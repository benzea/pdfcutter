
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject

class Bounds(object):
    def __init__(self):
        self.x1 = -1
        self.y1 = -1
        self.x2 = -1
        self.y2 = -1

class CanvasItem(GObject.Object):

    def __init__(self, **kwargs):
        GObject.Object.__init__(self)

        self._owner = kwargs['parent']
        self.bounds = Bounds()
        self._owner._children.append(self)

    def get_canvas(self):
        return self._owner

    def get_bounds(self):
        return self.bounds


    def do_button_press_event(self, *args):
        pass

    def do_button_release_event(self, *args):
        pass

    def do_button_motion_notify(self, *args):
        pass

    def do_focus_in_event(self, target_item, event):
        pass

    def do_focus_out_event(self, target_item, event):
        pass

    def remove(self):
        self._owner._children.remove(self)
        if self._owner._focused == self:
            self._owner._focused = None
        self._owner.queue_draw()

    def lower(self, below):
        idx = self._owner._children.index(below)
        self._owner._children.remove(self)
        self._owner._children.insert(idx - 1, self)
        self._owner.queue_draw()

    def raise_(self, above):
        idx = self._owner._children.index(above)
        self._owner._children.remove(self)
        self._owner._children.insert(idx + 1, self)
        self._owner.queue_draw()


class CanvasItemSimple(object):
    pass


class Event(object):
    def __init__(self):
        pass

class Canvas(Gtk.DrawingArea, Gtk.Scrollable):
    __gtype_name__ = "MiniGoo"

    def __init__(self):
        Gtk.DrawingArea.__init__(self)
        events = Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | \
            Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_MOTION_MASK | \
            Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.KEY_PRESS_MASK
        try:
            events = events | Gdk.EventMask.SMOOTH_SCROLL_MASK
        except AttributeError:
            # Does only work for GTK+ >=3.4
            pass
        self.add_events(events)

        self.hadj = None
        self.vadj = None
        self._hadj_value_changed_cb_id = None
        self._vadj_value_changed_cb_id = None

        self._scale = 1.0
        self.bounds = Bounds()

        self.props.can_focus = True

        self._children = []
        self._grabbed_item = None
        self._focused = None


    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_get_preferred_height(self):
        if self.vadj:
            self.vadj.props.upper = self.height

        return min(self.height, 300), self.height

    def do_get_preferred_width(self):
        if self.hadj:
            self.hadj.props.upper = self.width

        return min(self.width, 300), self.width

    def get_width(self):
        return (self.bounds.x2 - self.bounds.x1) * self._scale
    width = property(get_width)

    def get_height(self):
        return (self.bounds.y2 - self.bounds.y1) * self._scale
    height = property(get_height)

    def update_adjustments(self, allocation):
        if allocation is None:
            allocation = self.get_allocation()

        if self.hadj:
            self.hadj.props.page_size = min(self.width, allocation.width)
            if self.hadj.props.value > self.width - allocation.width:
                self.hadj.props.value = self.width - allocation.width
            self.hadj.props.page_increment = allocation.width * 0.9
            self.hadj.props.step_increment = allocation.width * 0.1
        if self.vadj:
            self.vadj.props.page_size = min(self.height, allocation.height)
            if self.vadj.props.value > self.height - allocation.height:
                self.vadj.props.value = self.height - allocation.height
            self.vadj.props.page_increment = allocation.height * 0.9
            self.vadj.props.step_increment = allocation.height * 0.1


    def do_size_allocate(self, allocation):
        # WTF? Why does this happen?
        if allocation.x < 0 or allocation.y < 0:
            GObject.idle_add(self.queue_resize)

        self.update_adjustments(allocation)
        Gtk.DrawingArea.do_size_allocate(self, allocation)

    def do_draw(self, cr):
        cr.set_source_rgb(1,1,1)
        cr.paint()

        bounds = Bounds()
        bounds.x1 = self.hadj.props.value / self._scale
        bounds.y1 = self.vadj.props.value / self._scale
        bounds.x2 = bounds.x1 + self.hadj.props.page_size / self._scale
        bounds.y2 = bounds.y1 + self.vadj.props.page_size / self._scale

        cr.scale(self._scale, self._scale)
        cr.translate(-bounds.x1, -bounds.y1)

        for c in self._children:
            cr.save()
            c.do_paint(cr, bounds, self._scale)
            cr.restore()

    def viewpixel_to_coordinate(self, x, y):
        x = self.bounds.x1 + (x + self.hadj.props.value) / self._scale
        y = self.bounds.y1 + (y + self.vadj.props.value) / self._scale
        return x, y

    def convert_from_pixels(self, x, y):
        # This is relative to the window for some reason (yeah, goocanvas API)
        x = x / self._scale
        y = y / self._scale
        return x, y

    def scroll_to(self, x, y):
        x = (x - self.bounds.x1) * self._scale
        y = (y - self.bounds.y1) * self._scale

        self.hadj.props.value = x
        self.vadj.props.value = y


    def _adjustment_changed_cb(self, adjustment):
        self.queue_draw()

    def get_hscroll_policy(self):
        # Does not matter, we don't support natural sizes
        return Gtk.ScrollablePolicy.NATURAL
    hscroll_policy = \
        GObject.property(get_hscroll_policy,
                         type=Gtk.ScrollablePolicy,
                         default=Gtk.ScrollablePolicy.NATURAL)

    def get_vscroll_policy(self):
        # Does not matter, we don't support natural sizes
        return Gtk.ScrollablePolicy.NATURAL
    vscroll_policy = \
        GObject.property(get_vscroll_policy,
                         type=Gtk.ScrollablePolicy,
                         default=Gtk.ScrollablePolicy.NATURAL)

    def get_vadjustment(self):
        return self.vadj

    def set_vadjustment(self, value):
        if self._vadj_value_changed_cb_id is not None:
            self.vadj.disconnect(self._vadj_value_changed_cb_id)
            self._vadj_value_changed_cb_id = None
        self.vadj = value

        if self.vadj is not None:
            self._vadj_value_changed_cb_id = self.vadj.connect('value-changed', self._adjustment_changed_cb)

        self.queue_draw()

    vadjustment = GObject.property(get_vadjustment, set_vadjustment, type=Gtk.Adjustment)

    def get_hadjustment(self):
        return self.hadj

    def set_hadjustment(self, value):
        if self._hadj_value_changed_cb_id is not None:
            self.hadj.disconnect(self._hadj_value_changed_cb_id)
            self._hadj_value_changed_cb_id = None
        self.hadj = value

        if self.hadj is not None:
            self._hadj_value_changed_cb_id = self.hadj.connect('value-changed', self._adjustment_changed_cb)

        self.queue_draw()

    hadjustment = GObject.property(get_hadjustment, set_hadjustment, type=Gtk.Adjustment)

    def set_scale(self, value):
        self._scale = value
        self.update_adjustments(None)
        self.queue_resize()

    def get_scale(self):
        return self._scale

    scale = GObject.property(get_scale, set_scale, float, minimum=0.001, maximum=1024.0, default=1.0)

    def get_root_item(self):
        # Just return self ...
        return self

    def get_true(self):
        return True
    redraw_when_scrolled = \
        GObject.property(get_true, type=bool, default=True)



    def set_bounds(self, x1, y1, x2, y2):
        self.bounds.x1 = x1
        self.bounds.y1 = y1
        self.bounds.x2 = x2
        self.bounds.y2 = y2
        self.queue_resize()

    def request_redraw(self, bounds):
        self.queue_draw()

    def grab_focus(self, item):
        if self._focused is not None:
            self._focused.do_focus_out_event(self._focused, None)
        self._focused = item
        if self._focused is not None:
            self._focused.do_focus_in_event(self._focused, None)
        self.queue_draw()




    # Input events
    def do_key_press_event(self, event):
        if self._focused is None:
            return

        return self._focused.do_key_press_event(None, event)


    def do_button_press_event(self, event):
        Gtk.Widget.grab_focus(self)
        x, y = self.viewpixel_to_coordinate(event.x, event.y)

        sub = Event()
        sub.x = x
        sub.y = y
        sub.button = event.button
        sub.state = event.state

        # Just assume the bounds are correct!
        for c in reversed(self._children):
            if c.do_simple_is_item_at(x, y, None, True):
                handled = c.do_button_press_event(None, sub)
                self._grabbed_item = c
                if handled:
                    return True
                # Do not propagate further
                return False
        return False


    def do_button_release_event(self, event):
        x, y = self.viewpixel_to_coordinate(event.x, event.y)

        sub = Event()
        sub.x = x
        sub.y = y
        sub.button = event.button
        sub.state = event.state

        # Prefer the one we have "grabbed"
        if self._grabbed_item is not None:
            item = self._grabbed_item
            self._grabbed_item = None
            return item.do_button_release_event(None, sub)

        # Just assume the bounds are correct!
        for c in reversed(self._children):
            if c.do_simple_is_item_at(x, y, None, True):
                handled = c.do_button_release_event(None, sub)
                if handled:
                    return True
                # Do not propagate further
                return False
        return False

    def do_motion_notify_event(self, event):
        x, y = self.viewpixel_to_coordinate(event.x, event.y)

        sub = Event()
        sub.x = x
        sub.y = y
        sub.state = event.state

        # Prefer the one we have "grabbed"
        if self._grabbed_item is not None:
            return self._grabbed_item.do_motion_notify_event(None, sub)

        # Just assume the bounds are correct!
        for c in reversed(self._children):
            if c.do_simple_is_item_at(x, y, None, True):
                handled = c.do_motion_notify_event(None, sub)
                if handled:
                    return True
                # Do not propagate further
                return False

        return False

    def request_update(self):
        self.queue_draw()

