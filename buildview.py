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
from gi.repository import Pango
from gi.repository import PangoCairo
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
_PADDING = 5

class Box(GooCanvas.CanvasItemSimple, GooCanvas.CanvasItem):
	__gtype_name__ = "PDFBuildBox"
	def __init__(self, canvas, box, **kwargs):
		super(Box, self).__init__(**kwargs)
		self._canvas = canvas
		self._box = box
		self.x = 0
		self.y = 0
		self.width = 1
		self.height = 1
		self.has_focus = False
		
		self._drag_active = False

		self.update_pos()

	def do_focus_in_event(self, target_item, event):
		if target_item == self:
			self.has_focus = True
			self._canvas._focus_in(self)
			self._canvas.request_redraw(self.bounds)

	def do_focus_out_event(self, target_item, event):
		if target_item == self:
			self.has_focus = False
			self._canvas._focus_out(self)
			self._canvas.request_redraw(self.bounds)

	def do_simple_create_path(self, cr):
		cr.rectangle(self.x, self.y, self.width, self.height)

	def do_simple_is_item_at(self, x, y, cr, is_pointer_event):
		if self.x <= x and self.x + self.width >= x and \
		   self.y <= y and self.y + self.height >= y:
			return True
		return False

	def update_pos(self):
		self._canvas.request_redraw(self.bounds)

		page = self._canvas._pages[self._box.dpage]
		self.x = self._box.dx
		self.y = self._box.dy
		self.width = self._box.width * self._box.dscale
		self.height = self._box.height * self._box.dscale
		self.x += page.x
		self.y += page.y

		self.bounds.x1 = self.x
		self.bounds.x2 = self.x + self.width
		self.bounds.y1 = self.y
		self.bounds.y2 = self.y + self.height

		self._canvas.request_update()
		self._canvas.request_redraw(self.bounds)

	def update_start_position(self):
		self._box_start_x = self._box.dx
		self._box_start_y = self._box.dy

	def do_button_press_event(self, target, event):
		if event.button == 1:
			self._drag_active = True
			self._drag_edge = self._get_edge(event.x, event.y)
			self._mouse_x = event.x
			self._mouse_y = event.y
			self._motion_happened = False
			self._no_motion_grab_focus = False

			if not self.has_focus and not self._canvas._item_in_focus_group(self):
				if event.state & Gdk.ModifierType.SHIFT_MASK:
						self._canvas._add_item_to_focus_group(self)
				else:
					self._canvas.grab_focus(self)
			else:
				# We still grab the focus if there was no motion, and shift
				# has not been pressed!
				if not (event.state & Gdk.ModifierType.SHIFT_MASK):
					self._no_motion_grab_focus = True

			for item in self._canvas._iter_focused_items():
				item.update_start_position()

	def do_button_release_event(self, target, event):
		if event.button == 1 and self._drag_active:
			self._drag_active = False

			if self._no_motion_grab_focus and not self._motion_happened:
				self._canvas.grab_focus(self)

	def do_key_press_event(self, target, event):
		keyname = Gdk.keyval_name(event.keyval)

		handled = False

		# Do the same thing for all focused items.
		for item in self._canvas._iter_focused_items():
			max_x = item._canvas._pages[item._box.dpage].width
			max_y = item._canvas._pages[item._box.dpage].height

			max_x -= item.width
			max_y -= item.height

			if keyname == 'Delete':
				item._canvas._model.remove_box(item._box)
				handled = True
			elif keyname == 'Left':
				item._box.dx = max(0, item._box.dx - 72.0 / 25.4)
				handled = True
			elif keyname == 'Right':
				item._box.dx = min(max_x, item._box.dx + 72.0 / 25.4)
				handled = True
			elif keyname == 'Up':
				item._box.dy = max(0, item._box.dy - 72.0 / 25.4)
				handled = True
			elif keyname == 'Down':
				item._box.dy = min(max_y, item._box.dy + 72.0 / 25.4)
				handled = True
			elif keyname == 'equal':
				item._box.dscale = 1.0
				handled = True

		if keyname == 'minus':
			self._canvas._model.move_boxes_down([item._box for item in self._canvas._iter_focused_items()])
			handled = True
		elif keyname == 'plus':
			self._canvas._model.move_boxes_up([item._box for item in self._canvas._iter_focused_items()])
			handled = True

		return handled

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

	def do_motion_notify_event(self, target, event):
		cursor = None
		edge = self._get_edge(event.x, event.y)

		if not self._drag_active:
			# Only do bottom right corner for resize for now ...
			if edge == _EDGE_RIGHT | _EDGE_BOTTOM:
				cursor = Gdk.CursorType.BOTTOM_RIGHT_CORNER
			elif edge == _BOX:
				cursor = Gdk.CursorType.FLEUR
		else:
			if self._drag_edge == _EDGE_RIGHT | _EDGE_BOTTOM:
				cursor = Gdk.CursorType.BOTTOM_RIGHT_CORNER
			else:
				cursor = Gdk.CursorType.FLEUR

		# This should always be not None ...
		if cursor:
			cursor = Gdk.Cursor(self._canvas.get_display(), cursor)
		self._canvas.get_window().set_cursor(cursor)

		if not self._drag_active:
			return True

		self._motion_happened = True

		if self._drag_edge == _BOX:
			self._drag_box(event)
		elif self._drag_edge == _EDGE_RIGHT | _EDGE_BOTTOM:
			self._scale_box(event)
		else:
			# We are not handling this event
			return False

		self._canvas._scroll_to_box(self)

		return True

	def _scale_box(self, event):
		max_x = self._canvas._pages[self._box.dpage].width
		max_y = self._canvas._pages[self._box.dpage].height

		x_pos = event.x - self._canvas._pages[self._box.dpage].x
		y_pos = event.y - self._canvas._pages[self._box.dpage].y

		max_scale = \
		    min((self._canvas._pages[self._box.dpage].width - self._box.dx) / float(self._box.width),
		        (self._canvas._pages[self._box.dpage].height - self._box.dy) / float(self._box.height))

		scale_x = (x_pos - self._box.dx) / float(self._box.width)
		scale_y = (y_pos - self._box.dy) / float(self._box.height)

		scale = min(max(scale_x, scale_y, 0.1), max_scale)

		self._box.dscale = scale

	def _drag_box(self, event):
		max_x = self._canvas._pages[self._box.dpage].width
		max_y = self._canvas._pages[self._box.dpage].height

		if event.y < self._canvas._pages[self._box.dpage].y - _PADDING:
			if self._box.dpage > 0:
				for item in self._canvas._iter_focused_items():
					item._box.dpage -= 1
					item._mouse_y -= _PADDING + max_y
		elif event.y > self._canvas._pages[self._box.dpage].y + \
		               self._canvas._pages[self._box.dpage].height + \
		               _PADDING:
			for item in self._canvas._iter_focused_items():
				item._box.dpage += 1
				item._mouse_y += _PADDING + max_y

		dx = event.x - self._mouse_x
		dy = event.y - self._mouse_y

		for item in self._canvas._iter_focused_items():
			item.move_box_relative_to_start(event.state, dx, dy)

	def move_box_relative_to_start(self, mod_state, dx, dy):
		max_x = self._canvas._pages[self._box.dpage].width
		max_y = self._canvas._pages[self._box.dpage].height

		new_x = self._box_start_x + dx
		new_y = self._box_start_y + dy

		self._box.dx = max(0, min(new_x, max_x - self.width))
		self._box.dy = max(0, min(new_y, max_y - self.height))

		if mod_state & Gdk.ModifierType.CONTROL_MASK:
			move_x = self._box.dx - self._box_start_x
			move_y = self._box.dy - self._box_start_y

			move_x = move_x / 72.0 * 25.4
			move_y = move_y / 72.0 * 25.4

			move_x = round(move_x / 2.5) * 2.5
			move_y = round(move_y / 2.5) * 2.5

			move_x = move_x * 72.0 / 25.4
			move_y = move_y * 72.0 / 25.4

			self._box.dx = self._box_start_x + move_x
			self._box.dy = self._box_start_y + move_y

		if mod_state & Gdk.ModifierType.SHIFT_MASK:
			move_x = abs(self._box.dx - self._box_start_x)
			move_y = abs(self._box.dy - self._box_start_y)
			if move_x > move_y:
				self._box.dy = self._box_start_y
			else:
				self._box.dx = self._box_start_x

		dx -= new_x - self._box.dx
		dy -= new_y - self._box.dy

	def do_simple_paint(self, cr, bounds):
		pass

	def do_paint(self, cr, bounds, scale):
		if ( bounds.x1 > self.x + self.width + 2 or \
		     bounds.y1 > self.y + self.height + 2 ) or \
		   ( bounds.x2 < self.x - 2 or bounds.y2 < self.y - 2 ):
			return

		cr.save()

		x_offset = self.x * scale
		y_offset = self.y * scale
		x_offset = x_offset - math.floor(x_offset)
		y_offset = y_offset - math.floor(y_offset)
		x_offset = -x_offset / scale
		y_offset = -y_offset / scale

		rscale = scale * self._box.dscale
		result = self._canvas._model.get_rendered_box_or_queue(self._box, rscale, x_offset, y_offset)
		if result is None:
			cr.translate(self.x + self.width / 2.0, self.y + self.height / 2.0)
			cr.set_source_rgb(0.4, 0.4, 0.4)
			extends = cr.text_extents("Loading ...")

			height = extends[3]
			width = extends[4]
			wscale = (self.width * 0.8) / width
			hscale = (self.height * 0.8) / height
			nscale = min(hscale, wscale)
			cr.translate(- width * nscale / 2.0 - extends[0] * nscale, - height * nscale / 2.0 - extends[1] * nscale)
			cr.scale(nscale, nscale)

			cr.move_to(0, 0)
			cr.show_text("Loading ...")
			cr.restore()
		else:
			image = result[0]
			iscale = result[1]
			x_offset = result[2]
			y_offset = result[3]
			cr.translate(self.x, self.y)
			cr.rectangle(0, 0, self.width, self.height)
			cr.translate(x_offset, y_offset)
			cr.scale(1 / iscale * self._box.dscale, 1 / iscale * self._box.dscale)
			cr.set_source_surface(image)
			cr.fill()
			cr.restore()

		if self.get_canvas().outlines:
			cr.save()
			lw = _LINE_WIDTH / scale
			cr.set_line_width(lw)
			cr.rectangle(self.x + lw/2, self.y + lw/2, self.width - lw, self.height - lw)
			if not self.has_focus and not self._canvas._item_in_focus_group(self):
				cr.set_source_rgba(1.0, 0, 0, 0.8)
			else:
				cr.set_source_rgba(0, 0, 1.0, 0.8)
			cr.stroke()
			cr.restore()


class Page(GooCanvas.CanvasItemSimple, GooCanvas.CanvasItem):
	__gtype_name__ = "PDFBuildPage"
	
	def __init__(self, model, page, x, y, **kwargs):
		super(Page, self).__init__(**kwargs)
		self.x = x
		self.y = y
		self._page = page
		self._model = model
		self.width, self.height = model.document.get_page(0).get_size()

	def do_simple_is_item_at(self, x, y, cr, is_pointer_event):
		if self.x <= x and self.x + self.width >= x and \
		   self.y <= y and self.y + self.height >= y:
			return True
		return False

	def do_simple_create_path(self, cr):
		cr.rectangle(self.x - 2, self.y - 2, self.width + 4, self.height + 4)

	def do_simple_paint(self, cr, bounds):
		pass

	def do_motion_notify_event(self, target, event):
		self.get_canvas().get_window().set_cursor(None)

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
		cr.restore()

		if self.get_canvas().grid:
			cr.save()
			cr.translate(0, self.y)
			for x in xrange(1, int(self.width / 72 * 2.54) + 1):
				cr.move_to((int(self.x * scale + x / 2.54 * 72 * scale) + 0.5) / scale, 0)
				cr.line_to((int(self.x * scale + x / 2.54 * 72 * scale) + 0.5) / scale, self.height)
				cr.set_line_width(1 / scale)
				cr.set_dash([4 / scale, 4 / scale])

			cr.translate(self.x, -self.y)
			for y in xrange(1, int(self.height / 72 * 2.54) + 1):
				cr.move_to(0, (int(self.y * scale + y / 2.54 * 72 * scale) + 0.5) / scale)
				cr.line_to(self.width, (int(self.y * scale + y / 2.54 * 72 * scale) + 0.5) / scale)
				cr.set_line_width(1 / scale)
				cr.set_dash([4 / scale, 4 / scale])

			cr.set_source_rgba(0, 0, 0, 0.6)
			cr.stroke()
			cr.restore()


		cr.save()
		font = Pango.FontDescription(model.HEADER_FONT)
		font.set_weight(Pango.Weight.BOLD)
		layout = PangoCairo.create_layout(cr)
		layout.set_text(self._model.header_text, len(self._model.header_text))
		layout.set_font_description(font)
		cr.translate(self.x, self.y)
		cr.move_to(model.PADDING, model.PADDING - 2)
		PangoCairo.show_layout(cr, layout)
		cr.show_page()
		cr.restore()


class BuildView(GooCanvas.Canvas):
	__gtype_name__ = 'BuildView'

	def __init__(self):
		GooCanvas.Canvas.__init__(self)
		self._model = None
		self._root = self.get_root_item()
		self._pages = []
		self._boxes = {}
		self._grid = True
		self._outlines = True
		self.props.redraw_when_scrolled = True

		self._focused_item = None
		self._focus_list = []

	def _add_item_to_focus_group(self, item):
		if item is not self._focused_item and item not in self._focus_list:
			self.request_redraw(item.bounds)
			self._focus_list.append(item)

	def _item_in_focus_group(self, item):
		return item in self._focus_list

	def _iter_focused_items(self):
		if self._focused_item is None:
			return
		yield self._focused_item

		for item in self._focus_list:
			yield item

	def _focus_in(self, item):
		self._focused_item = item

		for item in self._focus_list:
			# They need redrawing
			self.request_redraw(item.bounds)
		self._focus_list = []

	def _focus_out(self, item):
		self._focused_item = None

		for item in self._focus_list:
			# They need redrawing
			self.request_redraw(item.bounds)
		self._focus_list = []

	def set_model(self, model):
		if self._model:
			self._model.disconnect(self._page_rendered_id)
			self._model.disconnect(self._box_changed_id)
			self._model.disconnect(self._box_zpos_changed_id)
			self._model.disconnect(self._box_added_id)
			self._model.disconnect(self._box_removed_id)
			self._model.disconnect(self._header_text_changed_id)

		self._model = model
		self._page_rendered_id = self._model.connect("box-rendered", self._box_rendered_cb)
		self._box_changed_id = self._model.connect("box-changed", self._box_changed_cb)
		self._box_zpos_changed_id = self._model.connect("box-zpos-changed", self._box_zpos_changed_cb)
		self._box_added_id = self._model.connect("box-added", self._box_added_cb)
		self._box_removed_id = self._model.connect("box-removed", self._box_removed_cb)
		self._header_text_changed_id = self._model.connect("header-text-changed", self._header_text_changed_cb)

		for page in self._pages:
			page.remove()
		for box, dbox in self._boxes.iteritems():
			dbox.remove()
		self._pages = []
		self._boxes = {}

		self._add_page()
		self.set_size_request(600, 450)

		for box in self._model.iter_boxes():
			while box.dpage + 1 > len(self._pages):
				self._add_page()
			self._boxes[box] = Box(self, box, parent=self._root)

	def _add_page(self):
		y = _PADDING
		x = _PADDING

		pwidth, pheight = self._model.document.get_page(0).get_size()

		y += math.ceil(pheight + _PADDING) * len(self._pages)

		page = Page(self._model, len(self._pages), x, y, fill_color="black", parent=self._root)
		# XXX: Cannote move right to the top with None (wrong annotation)
		#      So move above first page ...
		if len(self._pages) > 0:
			page.lower(self._pages[0])
		self._pages.append(page)

		self.set_bounds(0, 0, pwidth + 2*_PADDING, math.ceil(pheight + _PADDING) * len(self._pages) + _PADDING * 3)

	def _remove_page(self):
		self._pages.pop(len(self._pages) - 1).remove()

		pwidth, pheight = self._model.document.get_page(0).get_size()

		self.set_bounds(0, 0, pwidth + 2*_PADDING, math.ceil(pheight + _PADDING) * len(self._pages) + _PADDING * 3)

	def _update_pages(self, min_pages=1):
		pages = min_pages
		for box in self._boxes.keys():
			pages = max(pages, box.dpage + 1)
		while pages > len(self._pages):
			self._add_page()
		while pages < len(self._pages):
			self._remove_page()

	def get_model(self):
		return self._model

	def set_grid(self, value):
		self._grid = value
		self.queue_draw()

	def get_grid(self):
		return self._grid

	def set_outlines(self, value):
		self._outlines = value
		self.queue_draw()

	def get_outlines(self):
		return self._outlines

	model = GObject.property(type=object, setter=set_model, getter=get_model)
	grid = GObject.property(type=bool, default=True, setter=set_grid, getter=get_grid)
	outlines = GObject.property(type=bool, default=True, setter=set_outlines, getter=get_outlines)

	def _box_rendered_cb(self, model, box):
		try:
			self.request_redraw(self._boxes[box].get_bounds())
		except KeyError:
			# Just ignore if it the box disappeared already
			pass

	def _scroll_to_box(self, box):
		x = box.x * self.get_scale()
		y = box.y * self.get_scale()
		w = box.width * self.get_scale()
		h = box.height * self.get_scale()
		self.get_vadjustment().clamp_page(y, y + h)
		self.get_hadjustment().clamp_page(x, x + w)

	def _header_text_changed_cb(self, model):
		self.queue_draw()

	def _box_changed_cb(self, model, box):
		self._update_pages()
		self._boxes[box].update_pos()

	def _box_zpos_changed_cb(self, model, box):
		prev = model.get_lower_box(box)
		if prev:
			self._boxes[box].lower(self._boxes[prev])

			# Work around bug #676746
			if hasattr(self._boxes[box], 'raise_'):
                        	self._boxes[box].raise_(self._boxes[prev])
                        else:
				getattr(self._boxes[box], 'raise')(self._boxes[prev])
		else:
			self._boxes[box].lower(self._pages[box.dpage])

			# Work around bug #676746
			if hasattr(self._boxes[box], 'raise_'):
                        	self._boxes[box].raise_(self._pages[box.dpage])
                        else:
				getattr(self._boxes[box], 'raise')(self._pages[box.dpage])

	def _box_added_cb(self, model, box):
		self._update_pages(box.dpage + 1)
		self._boxes[box] = Box(self, box, parent=self._root)
		self._scroll_to_box(self._boxes[box])

	def _box_removed_cb(self, model, box):
		dbox = self._boxes.pop(box)
		dbox.remove()
		self._update_pages()

	def do_scroll_event(self, event):
		if not event.state & Gdk.ModifierType.CONTROL_MASK:
			return False

		if event.direction == Gdk.ScrollDirection.UP:
			zoom = 1.25
		elif event.direction == Gdk.ScrollDirection.DOWN:
			zoom = 0.8
		else:
			return False

		if self.get_hadjustment() and self.get_vadjustment():
			# We cannot use x and y because those are wrong if a lot of
			# events come in fast
			mouse_x, mouse_y = event.x_root, event.y_root
			origin_x, origin_y, dummy = self.get_window().get_origin()
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

