# -*- coding: utf-8 -*-
# PDFCutter
#
# Copyright (C) 2009, Benjamin Berg <benjamin@sipsolutions.net>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or   
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of 
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the  
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import cairo
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GooCanvas
from gi.repository import GObject
import model
import math

_BOX = 1
_EDGE_TOP = 2
_EDGE_BOTTOM = 4
_EDGE_LEFT = 8
_EDGE_RIGHT = 16
_LINE_WIDTH = 2

class Box(GooCanvas.CanvasItemSimple, GooCanvas.CanvasItem):
	__gtype_name__ = "PDFViewBox"
	def __init__(self, canvas, box, **kwargs):
		super(Box, self).__init__(**kwargs)
		self._canvas = canvas
		self._box = box
		self.x = 0
		self.y = 0
		self.width = 1
		self.height = 1
		
		self._drag_active = False

		self.update_pos()

	def do_simple_create_path(self, cr):
		cr.rectangle(self.x, self.y, self.width, self.height)

	def do_simple_is_item_at(self, x, y, cr, is_pointer_event):
		if self.x <= x and self.x + self.width >= x and \
		   self.y <= y and self.y + self.height >= y:
			return True
		return False

	def update_pos(self):
		self._canvas.request_redraw(self.bounds)
		page = self._canvas._pages[self._box.spage]
		self.x = self._box.sx
		self.y = self._box.sy
		self.width = self._box.width
		self.height = self._box.height
		self.x += page.x
		self.y += page.y

		self.bounds.x1 = self.x
		self.bounds.x2 = self.x + self.width
		self.bounds.y1 = self.y
		self.bounds.y2 = self.y + self.height

		self._canvas.request_update()
		self._canvas.request_redraw(self.bounds)

	def _get_edge(self, x, y):
		edge = 0
		x = x - self.x
		y = y - self.y
		if y <= min(self.height * 0.2, _LINE_WIDTH * 5):
			edge |= _EDGE_TOP
		if self.height - y <= min(self.height * 0.2, _LINE_WIDTH * 5):
			edge |= _EDGE_BOTTOM
		if x <= min(self.width * 0.2, _LINE_WIDTH * 5):
			edge |= _EDGE_LEFT
		if self.width - x <= min(self.width * 0.2, _LINE_WIDTH * 5):
			edge |= _EDGE_RIGHT

		if edge == 0 and \
		   0 <= x <= self.width and \
		   0 <= y <= self.height:
			edge = _BOX
		return edge

	def do_button_press_event(self, target, event):
		if event.button == 1:
			if event.state & Gdk.ModifierType.CONTROL_MASK:
				self._canvas._model.remove_box(self._box)
				return True

			self._mouse_x = event.x
			self._mouse_y = event.y
			self._drag = self._get_edge(self._mouse_x, self._mouse_y)
			if self._drag:
				self._drag_active = True

	def do_button_release_event(self, target, event):
		if event.button == 1 and self._drag_active:
			self._drag_active = False

	def do_motion_notify_event(self, target, event):
		edge = self._get_edge(event.x, event.y)
		if edge == _EDGE_TOP:
			cursor = Gdk.CursorType.TOP_SIDE
		elif edge == _EDGE_BOTTOM:
			cursor = Gdk.CursorType.BOTTOM_SIDE
		elif edge == _EDGE_LEFT:
			cursor = Gdk.CursorType.LEFT_SIDE
		elif edge == _EDGE_RIGHT:
			cursor = Gdk.CursorType.RIGHT_SIDE
		elif edge == _EDGE_RIGHT | _EDGE_TOP:
			cursor = Gdk.CursorType.TOP_RIGHT_CORNER
		elif edge == _EDGE_RIGHT | _EDGE_BOTTOM:
			cursor = Gdk.CursorType.BOTTOM_RIGHT_CORNER
		elif edge == _EDGE_LEFT | _EDGE_TOP:
			cursor = Gdk.CursorType.TOP_LEFT_CORNER
		elif edge == _EDGE_LEFT | _EDGE_BOTTOM:
			cursor = Gdk.CursorType.BOTTOM_LEFT_CORNER
		elif edge == _BOX:
			cursor = Gdk.CursorType.FLEUR
		else:
			cursor = None

		if cursor:
			cursor = Gdk.Cursor(self._canvas.get_display(), cursor)
		self._canvas.get_window().set_cursor(cursor)

		if not self._drag_active:
			return False

		dx = event.x - self._mouse_x
		dy = event.y - self._mouse_y
		max_x = self._canvas._pages[self._box.spage].width
		max_y = self._canvas._pages[self._box.spage].height

		if self._drag == _BOX:
			new_x = self._box.sx + dx
			new_y = self._box.sy + dy

			self._box.sx = max(0, min(new_x, max_x - self._box.width))
			self._box.sy = max(0, min(new_y, max_y - self._box.height))

			dx -= new_x - self._box.sx
			dy -= new_y - self._box.sy
		if self._drag & _EDGE_TOP:
			dy = min(dy, self._box.height - 5)
			if self._box.sy + dy < 0:
				dy = -self._box.sy

			self._box.sy = self._box.sy + dy
			self._box.height = self._box.height - dy
		if self._drag & _EDGE_BOTTOM:
			dy = max(-self._box.height + 5, dy)
			dy = min(dy, max_y - self._box.height - self._box.sy)

			self._box.height += dy
		if self._drag & _EDGE_LEFT:
			dx = min(dx, self._box.width - 5)
			if self._box.sx + dx < 0:
				dx = -self._box.sx

			self._box.sx = self._box.sx + dx
			self._box.width = self._box.width - dx
		if self._drag & _EDGE_RIGHT:
			dx = max(-self._box.width + 5, dx)
			dx = min(dx, max_x - self._box.width - self._box.sx)

			self._box.width += dx

		self._mouse_x += dx
		self._mouse_y += dy

		return True

	def do_simple_paint(self, cr, bounds):
		pass

	def do_paint(self, cr, bounds, scale):
		if ( bounds.x1 > self.x + self.width + 2 or \
		     bounds.y1 > self.y + self.height + 2 ) or \
		   ( bounds.x2 < self.x - 2 or bounds.y2 < self.y - 2 ):
			return

		lw = _LINE_WIDTH / scale
		cr.set_line_width(lw)
		cr.rectangle(self.x + lw/2, self.y + lw/2, self.width - lw, self.height - lw)
		cr.set_source_rgba(1.0, 0, 0, 0.8)
		cr.stroke()

class Page(GooCanvas.CanvasItemSimple, GooCanvas.CanvasItem):
	__gtype_name__ = "PDFViewPage"
	
	def __init__(self, model, page, x, y, **kwargs):
		super(Page, self).__init__(**kwargs)
		self.x = x
		self.y = y
		self._page = page
		self._model = model
		self.width, self.height = model.document.get_page(page).get_size()
		self._drag_active = False

	def do_simple_is_item_at(self, x, y, cr, is_pointer_event):
		if self.x <= x and self.x + self.width >= x and \
		   self.y <= y and self.y + self.height >= y:
			return True
		return False

	def do_simple_create_path(self, cr):
		cr.rectangle(self.x - 2, self.y - 2, self.width + 4, self.height + 4)

	def do_simple_paint(self, cr, bounds):
		pass

	def do_paint(self, cr, bounds, scale):
		if ( bounds.x1 > self.x + self.width + 2 or \
		     bounds.y1 > self.y + self.height + 2 ) or \
		   ( bounds.x2 < self.x - 2 or bounds.y2 < self.y - 2 ):
			return

		cr.save()
		cr.set_source_rgb(0.3, 0.3, 0.3)
		cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
		cr.rectangle(self.x-1, self.y-1, self.width+2, self.height+2)
		cr.rectangle(self.x, self.y, self.width, self.height)
		cr.fill()

		x_offset = self.x * scale
		y_offset = self.y * scale
		x_offset = x_offset - math.floor(x_offset)
		y_offset = y_offset - math.floor(y_offset)
		x_offset = -x_offset / scale
		y_offset = -y_offset / scale
		result = self._model.get_rendered_page_or_queue(self._page, scale, x_offset, y_offset, cr.get_target())
		if result is None:
			cr.translate(self.x + self.width / 2.0, self.y + self.height / 2.0)
			cr.set_source_rgb(0.4, 0.4, 0.4)
			extends = cr.text_extents("Loading ...")

			height = extends[3]
			width = extends[4]
			scale = (self.width * 0.8) / width
			cr.translate(- width * scale / 2.0 - extends[0] * scale, - height * scale / 2.0 - extends[1] * scale)
			cr.scale(scale, scale)

			cr.move_to(0, 0)
			cr.show_text("Loading ...")
			cr.restore()
			return

		image = result[0]
		iscale = result[1]
		x_offset = result[2]
		y_offset = result[3]
		cr.rectangle(self.x, self.y, self.width, self.height)
		cr.translate(self.x, self.y)
		cr.translate(x_offset, y_offset)
		cr.scale(1 / iscale, 1 / iscale)
		cr.set_source_surface(image)
		cr.fill()

		cr.restore()

		if self._drag_active:
			cr.save()
			lw = _LINE_WIDTH / scale
			cr.set_line_width(lw)
			cr.set_source_rgb(1, 0, 0)

			x = min(self._drag_start_x, self._drag_end_x)
			width = abs(self._drag_start_x - self._drag_end_x)
			y = min(self._drag_start_y, self._drag_end_y)
			height = abs(self._drag_start_y - self._drag_end_y)

			cr.rectangle(x + lw/2, y + lw/2,
			             width - lw, height - lw)
			cr.stroke()
			cr.restore()

	def do_key_press_event(self, target, event):
		if Gdk.keyval_name(event.keyval) == 'Escape':
			self._drag_active = False

	def do_button_press_event(self, target, event):
		if event.button == 1:
			self._drag_start_x = event.x
			self._drag_start_y = event.y
			self._drag_end_x = event.x
			self._drag_end_y = event.y
			self._drag_active = True
			self.get_canvas().request_redraw(self.bounds)

	def do_button_release_event(self, target, event):
		if event.button == 1 and self._drag_active:
			self._drag_active = False
			self._drag_end_x = event.x
			self._drag_end_y = event.y

			box = model.Box()
			box.sx = min(self._drag_start_x, self._drag_end_x) - self.x
			box.width = abs(self._drag_start_x - self._drag_end_x)
			box.sy = min(self._drag_start_y, self._drag_end_y) - self.y
			box.height = abs(self._drag_start_y - self._drag_end_y)

			box.width = max(10, box.width)
			box.height = max(10, box.height)
			box.spage = self._page
			self._model.add_box(box)
			self.get_canvas().request_redraw(self.bounds)

	def do_motion_notify_event(self, target, event):
		self.get_canvas().get_window().set_cursor(None)
		if self._drag_active:
			self._drag_end_x = event.x
			self._drag_end_y = event.y
			self.get_canvas().request_redraw(self.bounds)

class PDFView(GooCanvas.Canvas):
	__gtype_name__ = 'PDFView'

	def __init__(self, page_label):
		GooCanvas.Canvas.__init__(self)
		self._model = None
		self._root = self.get_root_item()
		self._pages = []
		self._boxes = {}
		self._page_label = page_label
		self.props.redraw_when_scrolled = True

		self.add_events(Gdk.EventMask.SMOOTH_SCROLL_MASK)
		self._smooth_zoom = 0

		self.connect('draw', self.update_page_label)

	def set_model(self, model):
		if self._model:
			self._model.disconnect(self._page_rendered_id)
			self._model.disconnect(self._box_changed_id)
			self._model.disconnect(self._box_added_id)
			self._model.disconnect(self._box_removed_id)

		self._model = model
		self._page_rendered_id = self._model.connect("page-rendered", self._page_rendered_cb)
		self._box_changed_id = self._model.connect("box-changed", self._box_changed_cb)
		self._box_added_id = self._model.connect("box-added", self._box_added_cb)
		self._box_removed_id = self._model.connect("box-removed", self._box_removed_cb)

		for page in self._pages:
			page.remove()
		for box, dbox in self._boxes.iteritems():
			dbox.remove()
		self._pages = []
		self._boxes = {}

		PADDING = 5
		y = PADDING
		x = PADDING
		width = 0
		height = PADDING
		for i in xrange(self._model.document.get_n_pages()):
			page = Page(self._model, i, x, y, fill_color="black", parent=self._root)
			self._pages.append(page)

			y += PADDING
			y += math.ceil(page.height)
			width = max(width, page.width)
			height = math.ceil(page.y + page.height + PADDING)
		width = width + 2*PADDING

		self.set_bounds(0, 0, width, height)
		self.set_size_request(600, 450)

		for box in self._model.iter_boxes():
			self._boxes[box] = Box(self, box, parent=self._root)

	def get_model(self):
		return self._model

	model = GObject.property(type=object, setter=set_model, getter=get_model)

	def _page_rendered_cb(self, model, page):
		self.request_redraw(self._pages[page].get_bounds())

	def _box_changed_cb(self, model, box):
		self._boxes[box].update_pos()

	def _box_added_cb(self, model, box):
		self._boxes[box] = Box(self, box, parent=self._root)

	def _box_removed_cb(self, model, box):
		dbox = self._boxes.pop(box)
		dbox.remove()

	def update_page_label(self, *args):
		pages = len(self._pages)
		ypos = self.get_vadjustment().get_value()
		scale = self.get_scale()
		ypos = ypos / scale
		cur_page = -1
		good = False
		for i, page in enumerate(self._pages):
			if page.y <= ypos + 50:
				good = True
			if good and page.y + page.height >= ypos + 50:
				cur_page = i + 1
				break
		if cur_page == -1:
			cur_page = pages

		self._page_label.set_text("Seite %i von %i" % (cur_page, pages))

	def do_scroll_event(self, event):
		if not event.state & Gdk.ModifierType.CONTROL_MASK:
			return False

		if event.direction == Gdk.ScrollDirection.UP:
			zoom = 1.25
		elif event.direction == Gdk.ScrollDirection.DOWN:
			zoom = 0.8
		elif event.direction == Gdk.ScrollDirection.SMOOTH:
			self._smooth_zoom += event.delta_y

			if self._smooth_zoom < -1:
				zoom = 1.25
				self._smooth_zoom += 1
			elif self._smooth_zoom > 1:
				zoom = 0.8
				self._smooth_zoom -= 1
			else:
				return True
		else:
			return False

		if self.get_hadjustment() and self.get_vadjustment():
			# We cannot use x and y because those are wrong if a lot of
			# events come in fast
			mouse_x, mouse_y = event.x_root, event.y_root
			dummy, origin_x, origin_y = self.get_window().get_origin()

			mouse_x -= origin_x
			mouse_y -= origin_y
			mouse_x, mouse_y = self.convert_from_pixels(mouse_x, mouse_y)

			top_x, top_y = \
				self.convert_from_pixels(self.get_hadjustment().get_value(),
				                         self.get_vadjustment().get_value())
			x = top_x + mouse_x
			y = top_y + mouse_y

		scale = self.get_scale()
		
		if scale >= 4 and zoom > 1:
			return True
		if scale <= 0.2 and zoom < 1:
			return True
		
		scale *= zoom
		self.set_scale(scale)

		if self.get_hadjustment() and self.get_vadjustment():
			mouse_x /= zoom
			mouse_y /= zoom

			top_x = x - mouse_x
			top_y = y - mouse_y

			self.scroll_to(top_x, top_y)

		return True



