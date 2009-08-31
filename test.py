#! /usr/bin/env python

import gobject
import gtk
import poppler
import model
import pdfview
import goocanvas
import sys
from pdfview import PDFView
from buildview import BuildView

def clicked_cb(button):
	mod.emit_pdf("/tmp/test.pdf")

gtk.gdk.threads_init()

gtk.gdk.threads_enter()
win = gtk.Window(gtk.WINDOW_TOPLEVEL)

mod = model.Model(sys.argv[1])

box = model.Box()
box.width = 100
box.height = 100
box.page = 1
mod.add_box(box)

canvas = PDFView()
canvas.set_model(mod)
canvas.set_scale(1)

scroll = gtk.ScrolledWindow()
scroll.add(canvas)

hbox = gtk.HBox()
hbox.add(scroll)

canvas = BuildView()
canvas.set_model(mod)
canvas.set_scale(1)

scroll = gtk.ScrolledWindow()
scroll.add(canvas)

hbox.add(scroll)

vbox = gtk.VBox()
button = gtk.Button("Blub")
button.connect("clicked", clicked_cb)
vbox.pack_start(button, expand=False)
vbox.add(hbox)
win.add(vbox)
win.show_all()


gtk.main()
gtk.gdk.threads_leave()

