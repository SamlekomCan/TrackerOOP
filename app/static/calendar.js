/**
 * Calendar functionality for TimeTracker
 * Handles day, week, and month views with drag-and-drop support
 */

class Calendar {
    constructor(options) {
        this.viewType = options.viewType || 'month';
        this.currentDate = new Date(options.currentDate || new Date());
        this.container = document.getElementById('calendarContainer');
        this.apiUrl = options.apiUrl;
        this.dayPoTasksUrl = options.dayPoTasksUrl;
        this.isAdminOrManager = !!options.isAdminOrManager;
        this.events = [];
        this.tasks = [];
        this.timeEntries = [];
        
        // Filters
        this.showEvents = true;
        this.showTasks = true;
        this.showTimeEntries = true;
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadEvents();
    }
    
    setupEventListeners() {
        // View navigation
        document.getElementById('todayBtn')?.addEventListener('click', () => {
            this.currentDate = new Date();
            this.loadEvents();
        });
        
        document.getElementById('prevBtn')?.addEventListener('click', () => {
            this.navigatePrevious();
        });
        
        document.getElementById('nextBtn')?.addEventListener('click', () => {
            this.navigateNext();
        });
        
        // Filters
        document.getElementById('showEvents')?.addEventListener('change', (e) => {
            this.showEvents = e.target.checked;
            this.render();
        });
        
        document.getElementById('showTasks')?.addEventListener('change', (e) => {
            this.showTasks = e.target.checked;
            this.render();
        });
        
        document.getElementById('showTimeEntries')?.addEventListener('change', (e) => {
            this.showTimeEntries = e.target.checked;
            this.render();
        });
        
        // Modal close
        document.querySelectorAll('[data-dismiss="modal"]').forEach(btn => {
            btn.addEventListener('click', () => {
                const modalId = btn.dataset.modal || 'eventModal';
                document.getElementById(modalId).style.display = 'none';
            });
        });
    }
    
    navigatePrevious() {
        switch (this.viewType) {
            case 'day':
                this.currentDate.setDate(this.currentDate.getDate() - 1);
                break;
            case 'week':
                this.currentDate.setDate(this.currentDate.getDate() - 7);
                break;
            case 'month':
                this.currentDate.setMonth(this.currentDate.getMonth() - 1);
                break;
        }
        this.loadEvents();
    }
    
    navigateNext() {
        switch (this.viewType) {
            case 'day':
                this.currentDate.setDate(this.currentDate.getDate() + 1);
                break;
            case 'week':
                this.currentDate.setDate(this.currentDate.getDate() + 7);
                break;
            case 'month':
                this.currentDate.setMonth(this.currentDate.getMonth() + 1);
                break;
        }
        this.loadEvents();
    }
    
    async loadEvents() {
        const { start, end } = this.getDateRange();
        
        try {
            const url = new URL(this.apiUrl, window.location.origin);
            url.searchParams.append('start', start.toISOString());
            url.searchParams.append('end', end.toISOString());
            url.searchParams.append('include_tasks', 'true');
            url.searchParams.append('include_time_entries', 'true');
            
            const response = await fetch(url);
            const data = await response.json();
            
            // Parse items by type (all items come in the 'events' array with item_type in extendedProps)
            const allItems = data.events || [];
            this.events = allItems.filter(item => item.extendedProps?.item_type === 'event');
            this.tasks = allItems.filter(item => item.extendedProps?.item_type === 'task');
            this.timeEntries = allItems.filter(item => item.extendedProps?.item_type === 'time_entry');
            
            console.log('API Response:', {
                total: allItems.length,
                events: this.events.length,
                tasks: this.tasks.length,
                time_entries: this.timeEntries.length,
                summary: data.summary,
                rawData: data
            });
            
            this.render();
        } catch (error) {
            console.error('Error loading events:', error);
            this.container.innerHTML = '<div class="text-center text-red-500 py-12">Error loading calendar data</div>';
        }
    }
    
    getDateRange() {
        let start, end;
        
        switch (this.viewType) {
            case 'day':
                start = new Date(this.currentDate);
                start.setHours(0, 0, 0, 0);
                end = new Date(this.currentDate);
                end.setHours(23, 59, 59, 999);
                break;
                
            case 'week':
                const day = this.currentDate.getDay();
                const diff = this.currentDate.getDate() - day + (day === 0 ? -6 : 1); // Monday as start
                start = new Date(this.currentDate);
                start.setDate(diff);
                start.setHours(0, 0, 0, 0);
                end = new Date(start);
                end.setDate(start.getDate() + 6);
                end.setHours(23, 59, 59, 999);
                break;
                
            case 'month':
                start = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth(), 1);
                end = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth() + 1, 0, 23, 59, 59, 999);
                break;
        }
        
        return { start, end };
    }
    
    render() {
        this.updateTitle();
        
        console.log('Calendar rendering:', {
            viewType: this.viewType,
            eventsCount: this.events.length,
            tasksCount: this.tasks.length,
            timeEntriesCount: this.timeEntries.length,
            showEvents: this.showEvents,
            showTasks: this.showTasks,
            showTimeEntries: this.showTimeEntries
        });
        
        switch (this.viewType) {
            case 'day':
                this.renderDayView();
                break;
            case 'week':
                this.renderWeekView();
                break;
            case 'month':
                this.renderMonthView();
                break;
        }
    }
    
    updateTitle() {
        const titleEl = document.getElementById('calendarTitle');
        if (!titleEl) return;
        
        const options = { month: 'long', year: 'numeric' };
        
        switch (this.viewType) {
            case 'day':
                titleEl.textContent = this.currentDate.toLocaleDateString(undefined, { 
                    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' 
                });
                break;
            case 'week':
                const { start, end } = this.getDateRange();
                titleEl.textContent = `${start.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} - ${end.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}`;
                break;
            case 'month':
                titleEl.textContent = this.currentDate.toLocaleDateString(undefined, options);
                break;
        }
    }
    
    renderDayView() {
        const html = `
            <div class="calendar-day-view">
                <div class="time-slots">
                    ${this.renderTimeSlots()}
                </div>
                <div class="events-column">
                    ${this.renderDayEvents()}
                </div>
            </div>
        `;
        this.container.innerHTML = html;
    }
    
    renderTimeSlots() {
        const slots = [];
        for (let hour = 0; hour < 24; hour++) {
            const time = `${hour.toString().padStart(2, '0')}:00`;
            slots.push(`<div class="time-slot" data-hour="${hour}">${time}</div>`);
        }
        return slots.join('');
    }
    
    renderDayEvents() {
        const dayStart = new Date(this.currentDate);
        dayStart.setHours(0, 0, 0, 0);
        const dayEnd = new Date(this.currentDate);
        dayEnd.setHours(23, 59, 59, 999);
        
        let html = '<div class="day-events-container">';
        
        // Render events
        if (this.showEvents) {
            this.events.forEach(event => {
                const eventStart = new Date(event.start);
                if (eventStart >= dayStart && eventStart <= dayEnd) {
                    const time = eventStart.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
                    const eventTitle = this.escapeHtml(event.title);
                    const eventColor = event.color || '#3b82f6';
                    html += `
                        <div class="event-card event" data-id="${event.id}" data-type="event" style="border-left-color: ${eventColor}" onclick="window.calendar.showEventDetails(${event.id}, 'event')">
                            <i class="fas fa-calendar mr-2 text-blue-600 dark:text-blue-400"></i>
                            <strong>${eventTitle}</strong>
                            <br><small>${time}</small>
                        </div>
                    `;
                }
            });
        }
        
        // Render tasks
        if (this.showTasks) {
            this.tasks.forEach(task => {
                const taskTitle = this.escapeHtml(task.title);
                const priorityIcons = { urgent: '🔴', high: '🟠', medium: '🟡', low: '🟢' };
                const priorityIcon = priorityIcons[task.extendedProps?.priority] || '📋';
                html += `
                    <div class="event-card task" data-id="${task.id}" data-type="task" onclick="window.open('/tasks/${task.id}', '_blank')">
                        ${priorityIcon} <strong>${taskTitle}</strong>
                        <br><small>Due: ${task.start}</small>
                        <br><small class="text-xs">Status: ${task.extendedProps?.status || 'Unknown'}</small>
                    </div>
                `;
            });
        }
        
        // Render time entries
        if (this.showTimeEntries) {
            this.timeEntries.forEach(entry => {
                const entryStart = new Date(entry.start);
                if (entryStart >= dayStart && entryStart <= dayEnd) {
                    const startTime = entryStart.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
                    const entryTitle = this.escapeHtml(entry.title);
                    const notes = entry.notes ? `<br><small class="text-xs">${this.escapeHtml(entry.notes)}</small>` : '';
                    html += `
                        <div class="event-card time_entry" data-id="${entry.id}" data-type="time_entry">
                            ⏱ <strong>${entryTitle}</strong>
                            <br><small>${startTime}</small>
                            ${notes}
                        </div>
                    `;
                }
            });
        }
        
        html += '</div>';
        return html;
    }
    
    renderWeekView() {
        const { start } = this.getDateRange();
        const days = [];
        
        for (let i = 0; i < 7; i++) {
            const day = new Date(start);
            day.setDate(start.getDate() + i);
            days.push(day);
        }
        
        let html = '<div class="calendar-week-view"><table class="week-table"><thead><tr>';
        
        days.forEach(day => {
            const isToday = this.isToday(day);
            html += `<th class="${isToday ? 'today' : ''}">${day.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</th>`;
        });
        
        html += '</tr></thead><tbody>';
        
        // Time slots for each day
        for (let hour = 0; hour < 24; hour++) {
            html += '<tr>';
            days.forEach(day => {
                html += `<td class="week-cell" data-date="${day.toISOString()}" data-hour="${hour}">`;
                html += this.renderWeekCellEvents(day, hour);
                html += '</td>';
            });
            html += '</tr>';
        }
        
        html += '</tbody></table></div>';
        this.container.innerHTML = html;
    }
    
    renderWeekCellEvents(day, hour) {
        const cellStart = new Date(day);
        cellStart.setHours(hour, 0, 0, 0);
        const cellEnd = new Date(day);
        cellEnd.setHours(hour + 1, 0, 0, 0);
        
        let html = '';
        
        // Check events
        if (this.showEvents) {
            this.events.forEach(event => {
                const eventStart = new Date(event.start);
                if (eventStart >= cellStart && eventStart < cellEnd) {
                    const eventTitle = this.escapeHtml(event.title);
                    const eventColor = event.color || '#3b82f6';
                    html += `<div class="event-chip" style="background-color: ${eventColor}" onclick="window.calendar.showEventDetails(${event.id}, 'event')" title="${eventTitle}">📅 ${eventTitle}</div>`;
                }
            });
        }
        
        // Check tasks (only if they're due this hour)
        if (this.showTasks) {
            this.tasks.forEach(task => {
                const taskDate = new Date(task.start);
                // Show task if it's due on this day and hour 9 (morning)
                if (taskDate.toDateString() === day.toDateString() && hour === 9) {
                    const taskTitle = this.escapeHtml(task.title);
                    html += `<div class="event-chip task-chip" style="background-color: #f59e0b" onclick="window.open('/tasks/${task.id}', '_blank'); event.stopPropagation();" title="${taskTitle}">📋 ${taskTitle}</div>`;
                }
            });
        }
        
        // Check time entries
        if (this.showTimeEntries) {
            this.timeEntries.forEach(entry => {
                const entryStart = new Date(entry.start);
                if (entryStart >= cellStart && entryStart < cellEnd) {
                    const entryTitle = this.escapeHtml(entry.title);
                    html += `<div class="event-chip time-entry-chip" style="background-color: #10b981; opacity: 0.8; cursor: default;" onclick="event.stopPropagation();" title="${entryTitle}">⏱ ${entryTitle}</div>`;
                }
            });
        }
        
        return html;
    }
    
    renderMonthView() {
        const year = this.currentDate.getFullYear();
        const month = this.currentDate.getMonth();
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const startDate = new Date(firstDay);
        startDate.setDate(startDate.getDate() - (startDate.getDay() === 0 ? 6 : startDate.getDay() - 1));
        
        let html = '<div class="calendar-month-view"><table class="month-table"><thead><tr>';
        const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        weekdays.forEach(day => {
            html += `<th>${day}</th>`;
        });
        html += '</tr></thead><tbody>';
        
        const currentDate = new Date(startDate);
        for (let week = 0; week < 6; week++) {
            html += '<tr>';
            for (let day = 0; day < 7; day++) {
                const isCurrentMonth = currentDate.getMonth() === month;
                const isToday = this.isToday(currentDate);
                html += `<td class="month-cell ${!isCurrentMonth ? 'other-month' : ''} ${isToday ? 'today' : ''}" data-date="${currentDate.toISOString()}">`;
                html += `<div class="date-number">${currentDate.getDate()}</div>`;
                html += this.renderMonthCellEvents(currentDate);
                html += '</td>';
                currentDate.setDate(currentDate.getDate() + 1);
            }
            html += '</tr>';
        }
        
        html += '</tbody></table></div>';
        this.container.innerHTML = html;
        
        // Add click handlers for cells
        this.container.querySelectorAll('.month-cell').forEach(cell => {
            cell.addEventListener('click', (e) => {
                if (e.target.classList.contains('month-cell') || e.target.classList.contains('date-number')) {
                    const date = new Date(cell.dataset.date);
                    const dateStr = this.formatLocalDate(date);
                    if (this.isAdminOrManager) {
                        this.showDayPoTasks(dateStr);
                    } else {
                        window.location.href = `${window.calendarData.newEventUrl}?date=${dateStr}`;
                    }
                }
            });
        });
    }

    formatLocalDate(date) {
        // Format using local calendar date components, avoiding the UTC shift
        // that toISOString() introduces (which can land on the wrong day
        // depending on the browser's timezone offset).
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    }

    async showDayPoTasks(dateStr) {
        const modal = document.getElementById('dayPoTasksModal');
        const title = document.getElementById('dayPoTasksTitle');
        const body = document.getElementById('dayPoTasksBody');
        if (!modal || !body) return;

        title.textContent = `${this.escapeHtml('PO Activity')} — ${dateStr}`;
        body.innerHTML = '<div class="text-center py-6"><i class="fas fa-spinner fa-spin"></i></div>';
        modal.style.display = 'flex';

        try {
            const res = await fetch(`${this.dayPoTasksUrl}?date=${dateStr}`, { credentials: 'same-origin' });
            const data = await res.json();

            if (!res.ok) {
                body.innerHTML = `<p style="color:#ef4444;">${this.escapeHtml(data.error || 'Failed to load')}</p>`;
                return;
            }

            const mutedStyle = 'color:#9ca3af;';
            const renderItem = (item, isMeeting) => {
                const timeLabel = isMeeting ? `<span style="background:#0ea5e9;color:#fff;border-radius:4px;padding:2px 6px;font-size:0.8em;">${item.dueTime}</span> ` : '';
                return `
                    <div style="cursor:pointer; padding:8px 10px; border-radius:6px; margin-bottom:6px; background:rgba(148,163,184,0.08);" onclick="window.open('${item.url}', '_blank')">
                        ${timeLabel}<strong>${this.escapeHtml(item.assigneeName)}</strong>: ${this.escapeHtml(item.name)}
                        <span style="${mutedStyle}font-size:0.8em; display:block;">${this.escapeHtml(item.status)} &middot; ${this.escapeHtml(item.priority)}</span>
                    </div>
                `;
            };

            let html = '';
            html += `<h4 style="margin-top:0;">📅 Meeting</h4>`;
            if (data.meetings && data.meetings.length) {
                html += data.meetings.map(m => renderItem(m, true)).join('');
            } else {
                html += `<p style="${mutedStyle}">No meetings scheduled.</p>`;
            }

            html += `<h4>📋 Other Tasks</h4>`;
            if (data.other_tasks && data.other_tasks.length) {
                html += data.other_tasks.map(t => renderItem(t, false)).join('');
            } else {
                html += `<p style="${mutedStyle}">No other tasks.</p>`;
            }

            body.innerHTML = html;
        } catch (err) {
            body.innerHTML = `<p style="color:#ef4444;">Failed to load PO activity.</p>`;
        }
    }
    
    renderMonthCellEvents(day) {
        const dayStart = new Date(day);
        dayStart.setHours(0, 0, 0, 0);
        const dayEnd = new Date(day);
        dayEnd.setHours(23, 59, 59, 999);
        
        let html = '<div class="month-events">';
        let count = 0;
        const maxDisplay = 3;
        
        // Events
        if (this.showEvents) {
            this.events.forEach(event => {
                const eventStart = new Date(event.start);
                if (eventStart >= dayStart && eventStart <= dayEnd) {
                    if (count < maxDisplay) {
                        const eventTitle = this.escapeHtml(event.title);
                        const eventColor = event.color || '#3b82f6';
                        html += `<div class="event-badge" style="background-color: ${eventColor}" onclick="window.calendar.showEventDetails(${event.id}, 'event'); event.stopPropagation();" title="${eventTitle}">📅 ${eventTitle}</div>`;
                    }
                    count++;
                }
            });
        }
        
        // Tasks
        if (this.showTasks) {
            this.tasks.forEach(task => {
                const taskDate = new Date(task.start);
                if (taskDate.toDateString() === day.toDateString()) {
                    if (count < maxDisplay) {
                        const taskTitle = this.escapeHtml(task.title);
                        html += `<div class="event-badge task-badge" onclick="window.open('/tasks/${task.id}', '_blank'); event.stopPropagation();" title="${taskTitle}">📋 ${taskTitle}</div>`;
                    }
                    count++;
                }
            });
        }
        
        // Time entries
        if (this.showTimeEntries) {
            this.timeEntries.forEach(entry => {
                const entryStart = new Date(entry.start);
                if (entryStart >= dayStart && entryStart <= dayEnd) {
                    if (count < maxDisplay) {
                        const entryTitle = this.escapeHtml(entry.title);
                        html += `<div class="event-badge time-entry-badge" onclick="event.stopPropagation();" title="${entryTitle}">⏱ ${entryTitle}</div>`;
                    }
                    count++;
                }
            });
        }
        
        if (count > maxDisplay) {
            html += `<div class="event-badge-more">+${count - maxDisplay} more</div>`;
        }
        
        html += '</div>';
        return html;
    }
    
    isToday(date) {
        const today = new Date();
        return date.getDate() === today.getDate() &&
               date.getMonth() === today.getMonth() &&
               date.getFullYear() === today.getFullYear();
    }
    
    async showEventDetails(id, type) {
        // Navigate to the appropriate detail page
        if (type === 'event') {
            window.location.href = `/calendar/event/${id}`;
        } else if (type === 'task') {
            window.location.href = `/tasks/${id}`;
        } else if (type === 'time_entry') {
            // Time entries are displayed for context only - they're not clickable
            // Users can manage time entries via the Timer/Reports sections
            console.log('Time entry clicked:', id);
        }
    }
    
    escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text ? text.replace(/[&<>"']/g, m => map[m]) : '';
    }
}

// Initialize calendar when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    if (typeof window.calendarData !== 'undefined') {
        window.calendar = new Calendar({
            viewType: window.calendarData.viewType,
            currentDate: window.calendarData.currentDate,
            apiUrl: window.calendarData.apiUrl,
            dayPoTasksUrl: window.calendarData.dayPoTasksUrl,
            isAdminOrManager: window.calendarData.isAdminOrManager
        });
        
    }
});

