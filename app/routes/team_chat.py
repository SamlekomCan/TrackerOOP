"""
Team Chat routes
"""

from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required
from sqlalchemy import and_, or_

from app import db, socketio
from app.models import Project, User
from app.models.team_chat import ChatChannel, ChatChannelMember, ChatMessage, ChatReadReceipt
from app.utils.module_helpers import module_enabled

team_chat_bp = Blueprint("team_chat", __name__)


def _display_channel_name(channel, viewer_id):
    """Resolve the name to show for a channel from the given viewer's perspective.

    Direct-message channels store a "A & B" name snapshot taken at creation time
    (see api_create_direct_message), which goes stale if either user's display
    name changes afterwards. Recompute it live from the other member's current
    display name instead of trusting the stored value. Group/public channels
    just use their stored name as-is.
    """
    if channel.channel_type != "direct":
        return channel.name
    other_member = ChatChannelMember.query.filter(
        ChatChannelMember.channel_id == channel.id, ChatChannelMember.user_id != viewer_id
    ).first()
    if other_member and other_member.user:
        return other_member.user.display_name
    return channel.name


def _notify_mentions(mentions, channel):
    """Best-effort "you were mentioned" push notification.

    Never let a notification failure take down message sending: the message
    is already committed and broadcast by the time this runs, so a broken
    notification backend should degrade silently rather than turn a
    successful send into a 500 the client reports as "failed to send".
    """
    if not mentions:
        return
    try:
        # NOTE: app.utils.notification_service doesn't actually exist anywhere
        # in this codebase (same broken import is also present, pre-existing,
        # in time_approval_service.py / client_approval_service.py /
        # workflow_engine.py) — this always raises. Left as-is rather than
        # silently no-op'd so a real notification service, if one gets added
        # under this path later, starts working here for free; the try/except
        # is what actually matters for chat: never let this 404-module import
        # turn a successful message send into a request the client sees fail.
        from app.utils.notification_service import NotificationService

        service = NotificationService()
        channel_name = _display_channel_name(channel, current_user.id)
        for user_id in mentions:
            service.send_notification(
                user_id=user_id,
                title="You were mentioned",
                message=f"{current_user.display_name} mentioned you in {channel_name}",
                type="info",
                priority="high",
            )
    except Exception:
        from flask import current_app

        current_app.logger.warning("Failed to send mention notification", exc_info=True)


def _broadcast_new_message(channel_id, message):
    """Push a chat message to every channel member's personal room in real time.

    Reuses the existing `user_{id}` room that every authenticated page already
    joins on connect (see base.html's `join_user_room` emit) instead of a
    separate per-channel room, so no extra client-side join step is needed.
    """
    member_user_ids = [
        row[0] for row in db.session.query(ChatChannelMember.user_id).filter_by(channel_id=channel_id).all()
    ]
    payload = message.to_dict()
    for user_id in member_user_ids:
        socketio.emit("new_message", payload, room=f"user_{user_id}")


@team_chat_bp.route("/chat")
@login_required
@module_enabled("team_chat")
def chat_index():
    """Main chat interface"""
    # Get all channels user is member of
    channels = (
        ChatChannel.query.join(ChatChannelMember)
        .filter(ChatChannelMember.user_id == current_user.id, ChatChannel.is_archived == False)
        .order_by(ChatChannel.updated_at.desc())
        .all()
    )

    # Get direct messages (channels with type='direct' and 2 members)
    direct_channels = (
        ChatChannel.query.join(ChatChannelMember)
        .filter(
            ChatChannelMember.user_id == current_user.id,
            ChatChannel.channel_type == "direct",
            ChatChannel.is_archived == False,
        )
        .all()
    )

    return render_template("chat/index.html", channels=channels, direct_channels=direct_channels)


@team_chat_bp.route("/chat/channels/<int:channel_id>")
@login_required
@module_enabled("team_chat")
def chat_channel(channel_id):
    """View a specific chat channel"""
    channel = ChatChannel.query.get_or_404(channel_id)

    # Check membership
    membership = ChatChannelMember.query.filter_by(channel_id=channel_id, user_id=current_user.id).first()

    if not membership and not current_user.is_admin:
        flash(_("You don't have access to this channel"), "error")
        return redirect(url_for("team_chat.chat_index"))

    # Get messages
    messages = (
        ChatMessage.query.filter_by(channel_id=channel_id, is_deleted=False)
        .order_by(ChatMessage.created_at.asc())
        .limit(100)
        .all()
    )

    # Get channel members
    members = ChatChannelMember.query.filter_by(channel_id=channel_id).all()

    # Mark messages as read (batch load receipts to avoid N+1)
    message_ids = [m.id for m in messages]
    existing_receipts = (
        ChatReadReceipt.query.filter(
            ChatReadReceipt.message_id.in_(message_ids),
            ChatReadReceipt.user_id == current_user.id,
        ).all()
        if message_ids
        else []
    )
    receipt_by_message = {r.message_id: r for r in existing_receipts}
    for message in messages:
        if message.id not in receipt_by_message:
            db.session.add(ChatReadReceipt(message_id=message.id, user_id=current_user.id))

    db.session.commit()

    can_manage_members = _can_manage_channel_members(channel, membership)
    # Computed separately (not assigned onto `channel.name`) so it can never get
    # swept up by the db.session.commit() above and persisted as the stored name.
    channel_display_name = _display_channel_name(channel, current_user.id)

    # For the @mention autocomplete: only members other than yourself, since
    # parse_mentions() matches on username (see app/models/team_chat.py).
    mentionable_users = [
        {"user_id": m.user_id, "username": m.user.username, "display_name": m.user.display_name}
        for m in members
        if m.user and m.user_id != current_user.id
    ]

    return render_template(
        "chat/channel.html",
        channel=channel,
        channel_display_name=channel_display_name,
        mentionable_users=mentionable_users,
        messages=messages,
        members=members,
        can_manage_members=can_manage_members,
    )


@team_chat_bp.route("/chat/channels/<int:channel_id>/send-message", methods=["POST"])
@login_required
@module_enabled("team_chat")
def send_message(channel_id):
    """Send a message via form submission (supports attachments)"""
    import json
    import os

    channel = ChatChannel.query.get_or_404(channel_id)

    # Check membership
    membership = ChatChannelMember.query.filter_by(channel_id=channel_id, user_id=current_user.id).first()

    if not membership and not current_user.is_admin:
        flash(_("You don't have access to this channel"), "error")
        return redirect(url_for("team_chat.chat_channel", channel_id=channel_id))

    content = request.form.get("content", "").strip()
    attachment_data = request.form.get("attachment_data")

    if not content and not attachment_data:
        flash(_("Message cannot be empty"), "error")
        return redirect(url_for("team_chat.chat_channel", channel_id=channel_id))

    # Parse attachment data if provided
    attachment_url = None
    attachment_filename = None
    attachment_size = None
    message_type = "text"

    if attachment_data:
        try:
            attachment_info = json.loads(attachment_data)
            attachment_url = attachment_info.get("url")
            attachment_filename = attachment_info.get("filename")
            attachment_size = attachment_info.get("size")
            message_type = "file"
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError) as e:
            from flask import current_app

            current_app.logger.warning("Could not parse attachment data: %s", e)
            flash(_("Attachment data was invalid; message sent without attachment."), "warning")

    # Create message
    message = ChatMessage(
        channel_id=channel_id,
        user_id=current_user.id,
        message=content or attachment_filename or "",
        message_type=message_type,
        attachment_url=attachment_url,
        attachment_filename=attachment_filename,
        attachment_size=attachment_size,
    )

    # Parse mentions
    mentions = message.parse_mentions()
    if mentions:
        message.mentions = mentions

    db.session.add(message)

    # Update channel updated_at
    channel.updated_at = datetime.utcnow()

    db.session.commit()

    _broadcast_new_message(channel_id, message)

    _notify_mentions(mentions, channel)

    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True, "message": message.to_dict()})

    return redirect(url_for("team_chat.chat_channel", channel_id=channel_id))


@team_chat_bp.route("/api/chat/channels", methods=["GET", "POST"])
@login_required
@module_enabled("team_chat")
def api_channels():
    """Get or create channels"""
    if request.method == "POST":
        # Only admins and managers can create channels
        if not (current_user.is_admin or current_user.is_manager):
            return jsonify({"error": _("Only admins and managers can create channels")}), 403

        # Create new channel
        data = request.get_json()

        channel = ChatChannel(
            name=data.get("name"),
            description=data.get("description"),
            channel_type=data.get("channel_type", "public"),
            created_by=current_user.id,
            project_id=data.get("project_id"),
        )
        db.session.add(channel)
        db.session.flush()

        # Add creator as member
        member = ChatChannelMember(channel_id=channel.id, user_id=current_user.id, is_admin=True)
        db.session.add(member)

        # Add other members if specified
        if data.get("member_ids"):
            for user_id in data.get("member_ids", []):
                if user_id != current_user.id:
                    member = ChatChannelMember(channel_id=channel.id, user_id=user_id)
                    db.session.add(member)

        db.session.commit()

        return jsonify({"success": True, "channel": channel.to_dict()})

    # GET - List channels
    channels = (
        ChatChannel.query.join(ChatChannelMember)
        .filter(ChatChannelMember.user_id == current_user.id, ChatChannel.is_archived == False)
        .order_by(ChatChannel.updated_at.desc())
        .all()
    )

    channel_dicts = []
    for c in channels:
        d = c.to_dict()
        d["name"] = _display_channel_name(c, current_user.id)
        channel_dicts.append(d)

    return jsonify({"channels": channel_dicts})


def _can_manage_channel_members(channel, membership):
    """Global admins/managers, or a channel's own admin, can add/remove its members."""
    if channel.channel_type == "direct":
        return False
    if current_user.is_admin or current_user.is_manager:
        return True
    return bool(membership and membership.is_admin)


@team_chat_bp.route("/api/chat/channels/<int:channel_id>/members", methods=["GET", "POST"])
@login_required
@module_enabled("team_chat")
def api_channel_members(channel_id):
    """List or add members of a channel"""
    channel = ChatChannel.query.get_or_404(channel_id)
    membership = ChatChannelMember.query.filter_by(channel_id=channel_id, user_id=current_user.id).first()

    if request.method == "GET":
        if not membership and not current_user.is_admin:
            return jsonify({"error": _("Access denied")}), 403
        members = ChatChannelMember.query.filter_by(channel_id=channel_id).all()
        return jsonify(
            {
                "members": [
                    {
                        "user_id": m.user_id,
                        "username": m.user.username if m.user else None,
                        "display_name": m.user.display_name if m.user else None,
                        "is_admin": m.is_admin,
                    }
                    for m in members
                ]
            }
        )

    # POST - add members
    if not _can_manage_channel_members(channel, membership):
        return jsonify({"error": _("Only channel admins, managers, or admins can add members")}), 403

    data = request.get_json() or {}
    user_ids = data.get("user_ids") or []
    if not user_ids:
        return jsonify({"error": _("No users specified")}), 400

    existing_ids = {m.user_id for m in ChatChannelMember.query.filter_by(channel_id=channel_id).all()}
    added = []
    for user_id in user_ids:
        if user_id in existing_ids:
            continue
        user = User.query.get(user_id)
        if not user:
            continue
        db.session.add(ChatChannelMember(channel_id=channel_id, user_id=user_id))
        existing_ids.add(user_id)
        added.append(user_id)

    db.session.commit()
    return jsonify({"success": True, "added": added})


@team_chat_bp.route("/api/chat/channels/<int:channel_id>/members/<int:user_id>", methods=["DELETE"])
@login_required
@module_enabled("team_chat")
def api_channel_remove_member(channel_id, user_id):
    """Remove a member from a channel (or let a member remove themselves)"""
    channel = ChatChannel.query.get_or_404(channel_id)
    membership = ChatChannelMember.query.filter_by(channel_id=channel_id, user_id=current_user.id).first()

    is_self = user_id == current_user.id
    if not is_self and not _can_manage_channel_members(channel, membership):
        return jsonify({"error": _("Only channel admins, managers, or admins can remove members")}), 403

    target = ChatChannelMember.query.filter_by(channel_id=channel_id, user_id=user_id).first()
    if not target:
        return jsonify({"error": _("User is not a member of this channel")}), 404

    db.session.delete(target)
    db.session.commit()
    return jsonify({"success": True})


@team_chat_bp.route("/api/chat/channels/<int:channel_id>/messages", methods=["GET", "POST"])
@login_required
@module_enabled("team_chat")
def api_messages(channel_id):
    """Get or create messages"""
    channel = ChatChannel.query.get_or_404(channel_id)

    # Check membership
    membership = ChatChannelMember.query.filter_by(channel_id=channel_id, user_id=current_user.id).first()

    if not membership and not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403

    if request.method == "POST":
        # Create new message
        data = request.get_json()
        if data is None:
            return jsonify({"error": "Invalid JSON", "error_code": "validation_error"}), 400

        # Validate attachment fields if present (API may send attachment_url, attachment_filename, attachment_size)
        attachment_url = data.get("attachment_url")
        attachment_filename = data.get("attachment_filename")
        attachment_size = data.get("attachment_size")
        if attachment_url is not None or attachment_filename is not None or attachment_size is not None:
            errors = {}
            if attachment_url is not None and not isinstance(attachment_url, str):
                errors.setdefault("attachment_url", []).append("Must be a string.")
            if attachment_filename is not None and not isinstance(attachment_filename, str):
                errors.setdefault("attachment_filename", []).append("Must be a string.")
            if attachment_size is not None:
                try:
                    attachment_size = int(attachment_size)
                    if attachment_size < 0:
                        errors.setdefault("attachment_size", []).append("Must be non-negative.")
                except (TypeError, ValueError):
                    errors.setdefault("attachment_size", []).append("Invalid value.")
            if errors:
                from app.utils.api_responses import validation_error_response

                return validation_error_response(errors, message="Invalid attachment data.")

        message = ChatMessage(
            channel_id=channel_id,
            user_id=current_user.id,
            message=data.get("message", ""),
            message_type=data.get("message_type", "text"),
            reply_to_id=data.get("reply_to_id"),
            attachment_url=attachment_url,
            attachment_filename=attachment_filename,
            attachment_size=attachment_size,
        )

        # Parse mentions
        mentions = message.parse_mentions()
        if mentions:
            message.mentions = mentions

        db.session.add(message)
        db.session.commit()

        # Update channel updated_at
        channel.updated_at = datetime.utcnow()
        db.session.commit()

        _broadcast_new_message(channel_id, message)

        _notify_mentions(mentions, channel)

        return jsonify({"success": True, "message": message.to_dict()})

    # GET - List messages
    before_id = request.args.get("before_id", type=int)
    limit = request.args.get("limit", 50, type=int)

    query = ChatMessage.query.filter_by(channel_id=channel_id, is_deleted=False)

    if before_id:
        query = query.filter(ChatMessage.id < before_id)

    messages = query.order_by(ChatMessage.created_at.desc()).limit(limit).all()
    messages.reverse()  # Return in chronological order

    # Mark as read (batch load receipts to avoid N+1)
    message_ids = [m.id for m in messages]
    existing_receipts = (
        ChatReadReceipt.query.filter(
            ChatReadReceipt.message_id.in_(message_ids),
            ChatReadReceipt.user_id == current_user.id,
        ).all()
        if message_ids
        else []
    )
    receipt_by_message = {r.message_id: r for r in existing_receipts}
    for message in messages:
        if message.id not in receipt_by_message:
            db.session.add(ChatReadReceipt(message_id=message.id, user_id=current_user.id))

    db.session.commit()

    return jsonify({"messages": [m.to_dict() for m in messages]})


@team_chat_bp.route("/api/chat/messages/<int:message_id>", methods=["PUT", "DELETE"])
@login_required
@module_enabled("team_chat")
def api_message(message_id):
    """Update or delete message"""
    message = ChatMessage.query.get_or_404(message_id)

    if message.user_id != current_user.id and not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403

    if request.method == "PUT":
        # Update message
        data = request.get_json()
        message.message = data.get("message", message.message)
        message.is_edited = True
        message.edited_at = datetime.utcnow()

        # Re-parse mentions
        message.parse_mentions()

        db.session.commit()
        return jsonify({"success": True, "message": message.to_dict()})

    elif request.method == "DELETE":
        # Soft delete
        message.is_deleted = True
        db.session.commit()
        return jsonify({"success": True})


@team_chat_bp.route("/api/chat/messages/<int:message_id>/react", methods=["POST"])
@login_required
@module_enabled("team_chat")
def api_react(message_id):
    """Add or remove reaction to message"""
    message = ChatMessage.query.get_or_404(message_id)
    data = request.get_json()

    emoji = data.get("emoji")
    if not emoji:
        return jsonify({"error": "Emoji required"}), 400

    reactions = message.reactions or {}
    if emoji not in reactions:
        reactions[emoji] = []

    if current_user.id in reactions[emoji]:
        reactions[emoji].remove(current_user.id)
        if not reactions[emoji]:
            del reactions[emoji]
    else:
        reactions[emoji].append(current_user.id)

    message.reactions = reactions if reactions else None
    db.session.commit()

    return jsonify({"success": True, "reactions": reactions})


@team_chat_bp.route("/chat/channels/<int:channel_id>/messages/<int:message_id>/attachments/download")
@login_required
@module_enabled("team_chat")
def download_attachment(channel_id, message_id):
    """Download an attachment from a chat message"""
    import os

    from flask import current_app, send_file

    message = ChatMessage.query.get_or_404(message_id)

    # Verify message belongs to channel
    if message.channel_id != channel_id:
        flash(_("Invalid message"), "error")
        return redirect(url_for("team_chat.chat_channel", channel_id=channel_id))

    # Check membership
    membership = ChatChannelMember.query.filter_by(channel_id=channel_id, user_id=current_user.id).first()

    if not membership and not current_user.is_admin:
        flash(_("You don't have access to this channel"), "error")
        return redirect(url_for("team_chat.chat_index"))

    if not message.attachment_url:
        flash(_("No attachment found"), "error")
        return redirect(url_for("team_chat.chat_channel", channel_id=channel_id))

    # Build file path
    file_path = os.path.join(current_app.root_path, "..", message.attachment_url)

    if not os.path.exists(file_path):
        flash(_("File not found"), "error")
        return redirect(url_for("team_chat.chat_channel", channel_id=channel_id))

    return send_file(
        file_path,
        as_attachment=True,
        download_name=message.attachment_filename,
    )


@team_chat_bp.route("/chat/channels/<int:channel_id>/upload-attachment", methods=["POST"])
@login_required
@module_enabled("team_chat")
def upload_attachment(channel_id):
    """Upload an attachment for a chat message"""
    import os
    from datetime import datetime

    from flask import current_app, jsonify
    from werkzeug.utils import secure_filename

    channel = ChatChannel.query.get_or_404(channel_id)

    # Check membership
    membership = ChatChannelMember.query.filter_by(channel_id=channel_id, user_id=current_user.id).first()

    if not membership and not current_user.is_admin:
        return jsonify({"error": _("You don't have access to this channel")}), 403

    # File upload configuration
    ALLOWED_EXTENSIONS = {
        "png",
        "jpg",
        "jpeg",
        "gif",
        "pdf",
        "doc",
        "docx",
        "txt",
        "xls",
        "xlsx",
        "zip",
        "rar",
        "csv",
        "json",
    }
    UPLOAD_FOLDER = "app/static/uploads/chat_attachments"
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    def allowed_file(filename):
        return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

    if "file" not in request.files:
        return jsonify({"error": _("No file provided")}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": _("No file selected")}), 400

    # Use the file upload utility for proper validation
    from app.utils.file_upload import validate_file_upload

    # Normalize allowed extensions to include leading dots for validation
    normalized_allowed = {ext if ext.startswith(".") else "." + ext for ext in ALLOWED_EXTENSIONS}

    is_valid, error_msg = validate_file_upload(file, allowed_extensions=normalized_allowed, max_size=MAX_FILE_SIZE)
    if not is_valid:
        return jsonify({"error": _(error_msg)}), 400

    # Save file - secure_filename after validation
    original_filename = secure_filename(file.filename)
    if not original_filename:
        return jsonify({"error": _("Invalid filename")}), 400

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{channel_id}_{timestamp}_{original_filename}"

    # Ensure upload directory exists
    upload_dir = os.path.join(current_app.root_path, "..", UPLOAD_FOLDER)
    try:
        os.makedirs(upload_dir, exist_ok=True)
    except (OSError, IOError) as e:
        current_app.logger.error(f"Failed to create upload directory {upload_dir}: {e}")
        return jsonify({"error": _("Server error: Could not create upload directory")}), 500

    file_path = os.path.join(upload_dir, filename)
    try:
        file.save(file_path)
        file_size = os.path.getsize(file_path)
    except (OSError, IOError) as e:
        current_app.logger.error(f"Failed to save file {filename}: {e}")
        return jsonify({"error": _("Server error: Could not save file")}), 500

    # Return file info for message creation
    return jsonify(
        {
            "success": True,
            "attachment": {
                "url": os.path.join(UPLOAD_FOLDER, filename),
                "filename": original_filename,
                "size": file_size,
            },
        }
    )


@team_chat_bp.route("/api/chat/users", methods=["GET"])
@login_required
@module_enabled("team_chat")
def api_chat_users():
    """Get list of users for chat selection"""
    # Get all active users except current user
    # Order by full_name if available, otherwise by username
    users = (
        User.query.filter(User.id != current_user.id, User.is_active == True)
        .order_by(User.full_name, User.username)
        .all()
    )

    return jsonify({"users": [user.to_dict() for user in users]})


@team_chat_bp.route("/api/chat/direct-message/<int:user_id>", methods=["POST"])
@login_required
@module_enabled("team_chat")
def api_create_direct_message(user_id):
    """Create or find existing direct message channel with a user"""
    # CSRF token is validated automatically for form submissions
    # Get target user
    target_user = User.query.get_or_404(user_id)

    if target_user.id == current_user.id:
        return jsonify({"error": _("Cannot create direct message with yourself")}), 400

    if not target_user.is_active:
        return jsonify({"error": _("User is not active")}), 400

    # Check if direct message channel already exists
    # Direct messages have type='direct' and exactly 2 members
    existing_channels = (
        ChatChannel.query.join(ChatChannelMember)
        .filter(
            ChatChannel.channel_type == "direct",
            ChatChannel.is_archived == False,
            ChatChannelMember.user_id == current_user.id,
        )
        .all()
    )

    # Check each channel to see if it's a direct message with target_user
    for channel in existing_channels:
        members = [m.user_id for m in channel.members.all()]
        if len(members) == 2 and target_user.id in members:
            # Found existing direct message channel
            return jsonify({"success": True, "channel_id": channel.id, "channel": channel.to_dict()})

    # Create new direct message channel
    channel = ChatChannel(
        name=f"{current_user.display_name} & {target_user.display_name}",
        channel_type="direct",
        created_by=current_user.id,
    )
    db.session.add(channel)
    db.session.flush()

    # Add both users as members
    member1 = ChatChannelMember(channel_id=channel.id, user_id=current_user.id)
    member2 = ChatChannelMember(channel_id=channel.id, user_id=target_user.id)
    db.session.add(member1)
    db.session.add(member2)

    db.session.commit()

    return jsonify({"success": True, "channel_id": channel.id, "channel": channel.to_dict()})
