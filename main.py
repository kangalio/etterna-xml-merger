import os
from lxml import etree
from datetime import datetime
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

class UI(QApplication):
	root = None
	xml_list = None
	info = None
	app = None
	
	def __init__(self, app):
		super().__init__(["Kangalioo's Etterna.xml Merger"])
		self.app = app
		
		root = QWidget()
		self.root = root
		layout = QVBoxLayout(root)
		
		button = QPushButton("Add an Etterna.xml")
		layout.addWidget(button)
		button.setToolTip("Load one Etterna.xml save file into the program")
		button.clicked.connect(self.prompt_add_xml)
		
		info = QLabel()
		layout.addWidget(info)
		self.info = info
		info.setAlignment(Qt.AlignCenter)
		
		xml_list = QListWidget()
		layout.addWidget(xml_list)
		self.xml_list = xml_list
		xml_list.setWordWrap(True)
		
		button = QPushButton("Merge and save")
		self.save_btn = button
		layout.addWidget(button)
		button.setEnabled(False) # It's enabled as soon as XMLs are added
		button.setToolTip("Merge all loaded Etterna.xml's into one single one and save that")
		button.clicked.connect(self.prompt_merge_and_save)
		
		root.show()
	
	def prompt_add_xml(self):
		try:
			result = QFileDialog.getOpenFileName(filter="Etterna.xml files(*.xml)")
			path = result[0] # getOpenFileName returns tuple of path and filetype
			if path == "": return # If user cancelled the file chooser
			
			self.app.add_xml(path)
		except Exception as e:
			QMessageBox.warning(None, "Error occured", "An error occured. Maybe you've added an invalid XML file?")
			raise e
	
	def prompt_merge_and_save(self):
		out_path = QFileDialog.getSaveFileName(filter="Etterna.xml files(*.xml")
		if out_path is None: return # User cancelled dialog
		out_path = out_path[0]
		
		self.app.merge_and_save(out_path)

class App:
	ui = None
	xmls = []
	xml_trees = []
	
	score_keys_unique = []
	num_duplicates = 0
	
	def __init__(self):
		self.ui = UI(self)

	def run(self):
		self.ui.exec_()
	
	def add_xml(self, path):
		parser = etree.XMLParser(remove_blank_text=True)
		xml_tree = etree.parse(path, parser)
		xml = xml_tree.getroot()
		self.xml_trees.append(xml_tree)
		self.xmls.append(xml)
		
		self.ui.save_btn.setEnabled(True)
		self.update_info(xml)
		self.ui.xml_list.addItem(gen_xml_description(path, xml))
	
	def update_info(self, xml):
		for score in xml.iter("Score"):
			key = score.get("Key")
			if key in self.score_keys_unique:
				self.num_duplicates += 1
			else:
				self.score_keys_unique.append(key)
		
		num_unique = len(self.score_keys_unique)
		self.ui.info.setText(f"{num_unique} unique scores, {self.num_duplicates} duplicates")
		
	def merge_and_save(self, out_path):
		merged_xml = Merger(self.xmls).merge()
		# ~ exit() # REMEMBER
		QMessageBox.information(None, "Merging successful", "Merge was successful :)")
		etree.ElementTree(merged_xml).write(out_path, pretty_print=True)
		
		self.ui.quit()

class Merger:
	# Those are sorted by datetime of last scores, oldest to most recent
	xmls = None
	
	def __init__(self, xmls):
		def most_recent_score_datetime(xml):
			scores = xml.iter("Score")
			datetimes = [score.findtext("DateTime") for score in scores]
			return max(datetimes)
		
		# ~ self.xmls = sorted(xmls, key=most_recent_score_datetime)
		# don't sort because we want the user to have control about which xml has priority
		self.xmls = xmls
	
	# Returns the root Element of a new XML
	def merge(self):
		root = etree.Element("Stats")
		
		section_names = ["GeneralData", "Favorites", "PermaMirror", "Playlists", "ScoreGoals", "PlayerScores"]
		# it's a list of 6 lists, where each list corresponds to one of the above section names.
		# each list contains the relevant section for all xmls. So e.g. if you're merging three xmls
		# ideally this would be a list of 6 lists with three xml objects each.
		sections = []
		for section_name in section_names:
			section = []
			for xml in self.xmls:
				s = xml.find(section_name)
				if s is not None: section.append(s)
			sections.append(section)
		
		# General data is merged seperately
		root.append(self.merge_general_data(sections[0]))
		
		# All other section are merged more or less with a generic
		# method
		for i in range(1, len(sections)):
			if len(sections[i]) == 0:
				print(f"none of the xmls have {section_names[i]}, skipping")
				continue
			
			similar_fn = head_equals # function to check if duplicate
			if section_names[i] == "PlayerScores":
				similar_fn = Merger._custom_similarity_compare_1
			elif section_names[i] == "ScoreGoals":
				similar_fn = Merger._custom_similarity_compare_2
			
			generic_merge(sections[i], similar_fn)
			merged_section = sections[i][0]
			
			if not merged_section is None: root.append(merged_section)
		
		return root
	
	# It's only for PlayerScores merging
	def _custom_similarity_compare_1(e1, e2):
		if e1.tag == e2.tag:
			if e1.tag == "ScoresAt":
				return e1.get("Rate") == e2.get("Rate")
			elif e1.tag == "Chart":
				return e1.get("Key") == e2.get("Key")
			elif e1.tag == "Score":
				return e1.get("Key") == e2.get("Key")
		
		return head_equals(e1, e2)
	
	# This one's only for ScoreGoals merging
	def _custom_similarity_compare_2(e1, e2):
		if e1.tag == e2.tag and e1.tag == "ScoreGoal": return xml_equals(e1, e2)
		else: return head_equals(e1, e2)
	
	# Takes the base GeneralData as a base, but replaces its
	# "totals" (TotalSessions, TotalJumps etc.) with the sum of all
	# totals. The rest (i.e. modifiers, player rating...) stays the same
	def merge_general_data(self, elements):
		totals_names = ["TotalSessions", "TotalSessionSeconds",
			"TotalGameplaySeconds", "TotalDancePoints", "NumToasties",
			"TotalTapsAndHolds", "TotalJumps", "TotalHolds",
			"TotalRolls", "TotalMines", "TotalHands", "TotalLifts",
			"NumTotalSongsPlayed"]
		
		# TODO: reimplement the following with a dict (much cleaner)
		
		# Sum up the totals from each GeneralData
		totals = {total_name: 0 for total_name in totals_names}
		for element in elements:
			for total_name in totals_names:
				total_str = element.findtext(total_name)
				if total_str is None: continue
				totals[total_name] += int(total_str)
		
		# Take the most recent tree, but overwrite its totals with the
		# sum of all totals. Rest of the GeneralData stays the same
		
		# Remember, the xmls are sorted
		base_general_data = self.xmls[0].find("GeneralData") # Shouldn't be able to fail
		for (name, total) in totals.items():
			totals_elem = base_general_data.find(name)
			if totals_elem is None: # can happen if base general data is incomplete (i.e. EO-generated)
				print(f"creating GeneralData elem {name}")
				totals_elem = etree.SubElement(base_general_data, name)
			print(f"writing {total} into {totals_elem.tag}")
			totals_elem.text = str(total)
		
		return base_general_data
	

# Recursively merges multiple XML Elements into the first element in the
# list. Appends all direct children of all elements and removes
# duplicates (if an element is a duplicate is defined by the given
# similar_fn function).
def generic_merge(elements, similar_fn):
	if len(elements) == 0: return
	
	root = elements[0] # Use first element as main root to merge into
	
	for element in elements[1:]:
		for child in element:
			# Check if some element with same 'head' already exists
			brothers = [x for x in root if (similar_fn)(child, x)]
			if len(brothers) >= 1: # If yes:
				if len(brothers) > 1:
					# this should not happen regularly
					print(f"WARNING {len(brothers)} merge candidates available (there should only be one)")
				
				# Merge child's children into the element which is
				# already in the list
				to_be_merged_into = brothers[0]
				generic_merge([to_be_merged_into, child], similar_fn)
			else: # If no, just append directly
				root.append(child)

# Compares two XML elements for 'head equality' (i.e. ignoring
# children equality)
def head_equals(e1, e2):
    if e1.tag != e2.tag: return False
    #if e1.text != e2.text: return False # we consider it to be duplicates even if text doesn't match
    if e1.tail != e2.tail: return False
    if e1.attrib != e2.attrib: return False
    #if len(e1) != len(e2): return False
    #return all(xml_equal(c1, c2) for c1, c2 in zip(e1, e2))
    return True

# Compares two XML elements for equality. Checks recursively
def xml_equals(e1, e2):
	if not head_equals(e1, e2): return False
	if len(e1) != len(e2): return False
	return all(xml_equals(c1, c2) for c1, c2 in zip(e1, e2))

def parsedate(string):
	return datetime.strptime(string, "%Y-%m-%d %H:%M:%S")

def gen_xml_description(path, xml):
	scores = list(xml.iter("Score"))
	scores = sorted(scores, key=lambda score: score.findtext("DateTime"))
	start_date = scores[0].findtext("DateTime")[:10]
	end_date = scores[-1].findtext("DateTime")[:10]
	
	size_mb = round(os.path.getsize(path) / 1e6, 2)
	return f"{size_mb} MB, {len(scores)} scores from {start_date} to {end_date}"

app = App()
app.run()
