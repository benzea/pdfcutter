from model import Box, Model
import cairo


class Cutter(object):
	PADDING = 5

	def __init__(self, model):
		self.model = model
		self.page_boxes = []

	def add_box(self, box):
		placement = Box()
		placement.colored = box.colored
		placement.width = box.width
		placement.height = box.height
		placement.x = box.x

		if placement.height > self.height - self.PADDING * 2:
			raise AssertionError

		ypos = self.PADDING
		for pbox in self.page_boxes:
			if pbox.colored != placement.colored:
				ypos = max(ypos, pbox.y + pbox.height)
			else:
				if placement.x <= pbox.x + pbox.width and \
				   placement.x + placement.width >= pbox.x:
					ypos = pbox.y + pbox.height
				else:
					# Don't do anything
					pass
		placement.y = ypos

		if placement.y + placement.height > self.height - self.PADDING:
			self.new_page()
			self.add_box(box)
			return
		
		placement.y = ypos
		self.page_boxes.append(placement)

		# NOW DRAW THE BUGGER
		self.cr.save()
		
		self.cr.rectangle(placement.x, placement.y, box.width, box.height)
		self.cr.clip()

		self.cr.translate(0, placement.y - box.y)
		self.model.document.get_page(box.page).render_for_printing(self.cr)
		
		self.cr.restore()
	
	def write_pdf(self, filename):
		self.prepare_draw(filename)
		self.model.boxes.sort()
		
		for box in self.model.boxes:
			self.add_box(box)

		self.finish_draw()

	def new_page(self):
		self.cr.show_page()
		self.page_boxes = []

	def prepare_draw(self, filename):
		width, height = self.model.document.get_page(0).get_size()
		surface = cairo.PDFSurface(filename, width, height)
		self.ypos_n = self.PADDING
		self.ypos_y = self.PADDING
		self.height = height - self.PADDING * 2
		
		self.cr = cairo.Context(surface)

	def finish_draw(self):
		del self.cr

