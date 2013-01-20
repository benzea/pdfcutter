#! /usr/bin/env python
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

from gi.repository import GLib
GLib.threads_init()
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk
#Gdk.threads_init()
Gdk.threads_enter()

import os
import time
import sys

from pdfview import PDFView
from buildview import BuildView
from model import Model

dir = os.path.dirname(__file__)
sys.path.append(dir)


class MainWindow(object):

	def __init__(self) :
		self._builder = Gtk.Builder()
		self._builder.add_from_file(os.path.join(dir, 'main-window.ui'))
		self._model = None
		
		self._window = self._builder.get_object("pdfcutter")
		self._builder.connect_signals(self)
		self._window.maximize()

		scrolled_window = self._builder.get_object("pdf_view_scroll")
		self.pdf_view = PDFView()
		scrolled_window.add(self.pdf_view)

		scrolled_window = self._builder.get_object("build_view_scroll")
		self.build_view = BuildView()
		scrolled_window.add(self.build_view)

		grid_icon = Gtk.Image.new_from_file(os.path.join(dir, 'grid.png'))
		self._builder.get_object("grid_toggle").set_icon_widget(grid_icon)

		# So the buttons are insensitive
		self.update_ui()
		self._window.show_all()

		GObject.timeout_add(300000, self.autosave)

	def remove_status(self, context_id, message_id):
		statusbar = self._builder.get_object("statusbar")
		statusbar.remove(context_id, message_id)		

	def autosave(self):
		if self._model is None:
			return True

		statusbar = self._builder.get_object("statusbar")
		context_id = statusbar.get_context_id("autosave")

		if self._model.loadfile is None:
			message_id = statusbar.push(context_id, "Could not autosave, please save the project!")
		else:
			try:
				self._model.save_to_file(self._model.loadfile)
				message_id = statusbar.push(context_id, "Autosaved the project.")
			except:
				message_id = statusbar.push(context_id, "Error saving the project! Maybe try to save somewhere else.")

		GObject.timeout_add(30000, self.remove_status, context_id, message_id)

		return True

	def update_ui(self):
		if self._model:
			header_entry = self._builder.get_object('header_entry')
			header_entry.set_text(self._model.header_text)

			outlines_toggle = self._builder.get_object('outlines_toggle')
			outlines_toggle.set_active(self.build_view.outlines)

			grid_toggle = self._builder.get_object('grid_toggle')
			grid_toggle.set_active(self.build_view.grid)
			
	def outlines_toggled(self, *args):
		outlines_toggle = self._builder.get_object('outlines_toggle')
		self.build_view.outlines = outlines_toggle.get_active()

	def grid_toggled(self, *args):
		grid_toggle = self._builder.get_object('grid_toggle')
		self.build_view.grid = grid_toggle.get_active()

	def header_changed_cb(self, *args):
		if self._model:
			header_entry = self._builder.get_object('header_entry')
			self._model.set_header_text(header_entry.get_text())

	def export_pdf_pb_updater(self, pos, count, dialog, pbar):
		pbar.set_fraction(pos / float(count))

		if pos == count:
			dialog.response(Gtk.ResponseType.OK)
			dialog.destroy()

	def export_pdf(self, *args):
		if self._model is None:
			return

		fc = Gtk.FileChooserDialog(parent=self._window)
		pdf_filter = Gtk.FileFilter()
		pdf_filter.add_pattern('*.pdf')
		pdf_filter.set_name('PDF File')
		fc.add_button('gtk-cancel', Gtk.ResponseType.CANCEL)
		fc.add_button('gtk-save', Gtk.ResponseType.OK)
		fc.add_filter(pdf_filter)
		fc.set_action(Gtk.FileChooserAction.SAVE)
		result = fc.run()
		if result == Gtk.ResponseType.OK:
			fc.hide()
			filename = fc.get_filename()
			if not filename.endswith('.pdf'):
				filename += '.pdf'

			dialog = Gtk.Dialog(title="Creating PDF %s" % filename,
			                    parent=self._window,
			                    flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT)
			pbar = Gtk.ProgressBar()
			dialog.get_content_area().add(pbar)
			pbar.show()

			self._model.emit_pdf(filename, self.export_pdf_pb_updater, dialog, pbar)

			# Just return, the dialog will be destroyed by the pb updater
			dialog.show()

		fc.destroy()

	def export_png(self, *args):
		if self._model is None:
			return

		fc = Gtk.FileChooserDialog(parent=self._window)
		pdf_filter = Gtk.FileFilter()
		pdf_filter.add_pattern('*.tif')
		pdf_filter.set_name('Monochrome TIF File')
		fc.add_button('gtk-cancel', Gtk.ResponseType.CANCEL)
		fc.add_button('gtk-save', Gtk.ResponseType.OK)
		fc.add_filter(pdf_filter)
		fc.set_action(Gtk.FileChooserAction.SAVE)
		result = fc.run()
		if result == Gtk.ResponseType.OK:
			fc.hide()
			filename = fc.get_filename()
			if not filename.endswith('.tif'):
				filename += '.tif'

			dialog = Gtk.Dialog(title="Creating monochrome TIF File %s" % filename,
			                    parent=self._window,
			                    flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT)
			pbar = Gtk.ProgressBar()
			dialog.get_content_area().add(pbar)
			pbar.show()

			self._model.emit_tif(filename, self.export_pdf_pb_updater, dialog, pbar)

			# Just return, the dialog will be destroyed by the pb updater
			dialog.show()

		fc.destroy()

	def save_to_file_with_error_dialog(self, filename):
		try:
			self._model.save_to_file(filename)
		except:
			msg = Gtk.MessageDialog(parent=self._window, type=Gtk.MessageType.WARNING)
			msg.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
			msg.set_markup("Error saving data to file!")
			msg.format_secondary_markup("Maybe try to store the file somewhere else?")
			msg.run()
			msg.destroy()

	def save_file_as(self, *args):
		if self._model is None:
			return

		fc = Gtk.FileChooserDialog(parent=self._window)
		bcut_filter = Gtk.FileFilter()
		bcut_filter.add_pattern('*.bcut')
		bcut_filter.set_name('Britzel Cutter File')
		fc.add_button('gtk-cancel', Gtk.ResponseType.CANCEL)
		fc.add_button('gtk-save', Gtk.ResponseType.OK)
		fc.add_filter(bcut_filter)
		fc.set_action(Gtk.FileChooserAction.SAVE)
		result = fc.run()
		if result == Gtk.ResponseType.OK:
			filename = fc.get_filename()
			if not filename.endswith('.bcut'):
				filename += '.bcut'

			self.save_to_file_with_error_dialog(filename)
		fc.destroy()

	def save_file(self, *args):
		if self._model is None:
			return
		filename = self._model.loadfile
		if filename is None:
			return self.save_file_as()
		self.save_to_file_with_error_dialog(filename)

	def new_file(self, *args):
		fc = Gtk.FileChooserDialog(parent=self._window)
		fc.add_button('gtk-cancel', Gtk.ResponseType.CANCEL)
		fc.add_button('gtk-open', Gtk.ResponseType.OK)
		pdf_filter = Gtk.FileFilter()
		pdf_filter.add_pattern('*.pdf')
		pdf_filter.set_name('PDF File')
		fc.add_filter(pdf_filter)
		result = fc.run()
		if result == Gtk.ResponseType.OK:
			uri = fc.get_filename()
			model = Model(pdffile=uri)
			self.pdf_view.props.model = model
			self.build_view.props.model = model
			self._model = model
			self.update_ui()
		fc.destroy()
	
	def open_file(self, *args):
		fc = Gtk.FileChooserDialog(parent=self._window)
		bcut_filter = Gtk.FileFilter()
		bcut_filter.add_pattern('*.bcut')
		bcut_filter.set_name('Britzel Cutter File')
		fc.add_button('gtk-cancel', Gtk.ResponseType.CANCEL)
		fc.add_button('gtk-open', Gtk.ResponseType.OK)
		fc.add_filter(bcut_filter)
		result = fc.run()
		if result == Gtk.ResponseType.OK:
			filename = fc.get_filename()
			self.load_file(filename)
		fc.destroy()

	def load_file(self, filename):
		model = Model(loadfile=filename)
		self.pdf_view.props.model = model
		self.build_view.props.model = model
		self._model = model
		self.update_ui()
		
	def show_about_dialog(self, *args):
		about_dialog = Gtk.AboutDialog()
		about_dialog.set_authors(["Benjamin Berg <benjamin@sipsolutions.net>"])
		about_dialog.set_comments("Britzel Cut, ein PDF zuschneide tool für die Fachschaft Elektro- und Informationstechnik Universität Karlsruhe")
		about_dialog.set_program_name("Britzel Cut")
		about_dialog.set_website("https://fachschaft.etec.uni-karlsruhe.de/trac/fs_etec/")
		about_dialog.run()
		about_dialog.destroy()
	
	def quit_application(self, *args):
		buttons = (Gtk.STOCK_CLOSE, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
		dialog = Gtk.MessageDialog(
		    parent=self._window,
		    flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
		    type=Gtk.MessageType.WARNING,
		    buttons=Gtk.ButtonsType.NONE)
		dialog.set_markup("<b>Britzel Cut schließen?</b>")
		dialog.format_secondary_text("Sind Sie sicher, dass Sie Britzel Cut beenden wollen?")
		dialog.set_title("Britzel Cut schließen?")
		dialog.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
		result = dialog.run()
		if result == Gtk.ResponseType.OK:
			Gtk.main_quit()
		else:
			dialog.destroy()
			return True

win = MainWindow()

args = sys.argv[1:]
if args:
    if args[0] == '--nothreads':
        args.pop(0)

        import model
        model.no_threads = True

if len(args) == 1:
	win.load_file(sys.argv[1])

def url_hook(dialog, link):
	Gtk.show_uri(dialog.get_screen(), Gdk.CURRENT_TIME)

Gtk.main()
Gdk.threads_leave()

