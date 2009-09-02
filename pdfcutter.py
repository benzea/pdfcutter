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

import gobject
import gtk
import gtk.glade
import os
import time
import sys

from pdfview import PDFView
from buildview import BuildView
from model import Model
from cutter import Cutter

gtk.gdk.threads_init()
gtk.gdk.threads_enter()

class MainWindow(object):

	def __init__(self) :
		self._glade = gtk.glade.XML(os.path.join('./main_window.glade'))
		self._model = None
		
		self._window = self._glade.get_widget("pdfcutter")
		self._glade.signal_autoconnect(self)
		self._window.maximize()

		scrolled_window = self._glade.get_widget("pdf_view_scroll")
		self.pdf_view = PDFView()
		scrolled_window.add(self.pdf_view)

		scrolled_window = self._glade.get_widget("build_view_scroll")
		self.build_view = BuildView()
		scrolled_window.add(self.build_view)
		
		# So the buttons are insensitive
		self.update_ui()
		self._window.show_all()

		gobject.timeout_add(300000, self.autosave)

	def remove_status(self, context_id, message_id):
		statusbar = self._glade.get_widget("statusbar")
		statusbar.remove(context_id, message_id)		

	def autosave(self):
		if self._model is None:
			return True

		statusbar = self._glade.get_widget("statusbar")
		context_id = statusbar.get_context_id("autosave")

		if self._model.loadfile is None:
			message_id = statusbar.push(context_id, "Could not autosave, please save the project!")
		else:
			self._model.save_to_file(self._model.loadfile)
			message_id = statusbar.push(context_id, "Autosaved the project.")

		gobject.timeout_add(30000, self.remove_status, context_id, message_id)
		
		return True

	def update_ui(self):
		if self._model:
			header_entry = self._glade.get_widget('header_entry')
			header_entry.set_text(self._model.header_text)

			outlines_toggle = self._glade.get_widget('outlines_toggle')
			outlines_toggle.set_active(self.build_view.outlines)

			grid_toggle = self._glade.get_widget('grid_toggle')
			grid_toggle.set_active(self.build_view.grid)
			
	def outlines_toggled(self, *args):
		outlines_toggle = self._glade.get_widget('outlines_toggle')
		self.build_view.outlines = outlines_toggle.get_active()

	def grid_toggled(self, *args):
		grid_toggle = self._glade.get_widget('grid_toggle')
		self.build_view.grid = grid_toggle.get_active()

	def header_changed_cb(self, *args):
		if self._model:
			header_entry = self._glade.get_widget('header_entry')
			self._model.set_header_text(header_entry.get_text())

	def export_pdf_pb_updater(self, pos, count, dialog, pbar):
		pbar.set_fraction(pos / float(count))

		if pos == count:
			dialog.response(gtk.RESPONSE_OK)

	def export_pdf(self, *args):
		if self._model is None:
			return

		fc = gtk.FileChooserDialog(parent=self._window)
		pdf_filter = gtk.FileFilter()
		pdf_filter.add_pattern('*.pdf')
		pdf_filter.set_name('PDF File')
		fc.add_button('gtk-cancel', gtk.RESPONSE_CANCEL)
		fc.add_button('gtk-save', gtk.RESPONSE_OK)
		fc.add_filter(pdf_filter)
		fc.set_action(gtk.FILE_CHOOSER_ACTION_SAVE)
		result = fc.run()
		if result == gtk.RESPONSE_OK:
			fc.hide()
			filename = fc.get_filename()

			dialog = gtk.Dialog(title="Creating PDF %s" % filename,
			                    parent=self._window,
			                    flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT)
			pbar = gtk.ProgressBar()
			dialog.get_content_area().add(pbar)
			pbar.show()

			self._model.emit_pdf(filename, self.export_pdf_pb_updater, dialog, pbar)

			result = dialog.run()
			dialog.destroy()
			del dialog

		fc.destroy()

	def save_file_as(self, *args):
		if self._model is None:
			return

		fc = gtk.FileChooserDialog(parent=self._window)
		bcut_filter = gtk.FileFilter()
		bcut_filter.add_pattern('*.bcut')
		bcut_filter.set_name('Britzel Cutter File')
		fc.add_button('gtk-cancel', gtk.RESPONSE_CANCEL)
		fc.add_button('gtk-save', gtk.RESPONSE_OK)
		fc.add_filter(bcut_filter)
		fc.set_action(gtk.FILE_CHOOSER_ACTION_SAVE)
		result = fc.run()
		if result == gtk.RESPONSE_OK:
			filename = fc.get_filename()
			self._model.save_to_file(filename)
		fc.destroy()

	def save_file(self, *args):
		if self._model is None:
			return
		filename = self._model.loadfile
		if filename is None:
			return self.save_file_as()
		self._model.save_to_file(filename)

	def new_file(self, *args):
		fc = gtk.FileChooserDialog(parent=self._window)
		fc.add_button('gtk-cancel', gtk.RESPONSE_CANCEL)
		fc.add_button('gtk-open', gtk.RESPONSE_OK)
		pdf_filter = gtk.FileFilter()
		pdf_filter.add_pattern('*.pdf')
		pdf_filter.set_name('PDF File')
		fc.add_filter(pdf_filter)
		result = fc.run()
		if result == gtk.RESPONSE_OK:
			uri = fc.get_uri()
			model = Model(pdffile=uri)
			self.pdf_view.props.model = model
			self.build_view.props.model = model
			self._model = model
			self.update_ui()
		fc.destroy()
	
	def open_file(self, *args):
		fc = gtk.FileChooserDialog(parent=self._window)
		bcut_filter = gtk.FileFilter()
		bcut_filter.add_pattern('*.bcut')
		bcut_filter.set_name('Britzel Cutter File')
		fc.add_button('gtk-cancel', gtk.RESPONSE_CANCEL)
		fc.add_button('gtk-open', gtk.RESPONSE_OK)
		fc.add_filter(bcut_filter)
		result = fc.run()
		if result == gtk.RESPONSE_OK:
			filename = fc.get_filename()
			model = Model(loadfile=filename)
			self.pdf_view.props.model = model
			self.build_view.props.model = model
			self._model = model
			self.update_ui()
		fc.destroy()

	def show_about_dialog(self, *args):
		about_dialog = gtk.AboutDialog()
		about_dialog.set_authors(["Benjamin Berg <benjamin@sipsolutions.net>"])
		about_dialog.set_comments("Britzel Cut, ein PDF zuschneide tool für die Fachschaft Elektro- und Informationstechnik Universität Karlsruhe")
		about_dialog.set_program_name("Britzel Cut")
		about_dialog.set_website("https://fachschaft.etec.uni-karlsruhe.de/trac/fs_etec/")
		about_dialog.run()
		about_dialog.destroy()
	
	def quit_application(self, *args):
		gtk.main_quit()

win = MainWindow()

def url_hook(dialog, link):
	gtk.show_uri(dialog.get_screen(), gtk.gdk.CURRENT_TIME)

gtk.about_dialog_set_url_hook(url_hook)
gtk.main()
gtk.gdk.threads_leave()

