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


import poppler

class Box(object):
	def __init__(self):
		self.page = 0
		self.x = 0
		self.y = 0
		self.width = 100
		self.height = 100
		
		# This can be true or false, ie. switches the "color" used
		# for layout purposes
		self.colored = False

	def __cmp__(self, other):
		if self.page < other.page:
			return -1
		if self.page > other.page:
			return 1
		if self.y < other.y:
			return -1
		if self.y > other.y:
			return 1
		if self.x < other.x:
			return -1
		if self.x > other.x:
			return 1
		return 0

class Model(object):
	
	def __init__(self, filename):
		self.filename = filename
		self.document = \
			poppler.document_new_from_file(self.filename, None)
		self.boxes = []
	
	def sort_boxes():
		self.boxes.sort()

