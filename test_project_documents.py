"""Document identification and geometry preservation during reorganization."""

from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from drawing_title_block import title_block_svg
from project_documents import DRAWINGS, document_path, expand_drawing_targets
from reorganize_project import update_sheet


NS = {'s':'http://www.w3.org/2000/svg'}
SETTINGS = {'author':'Ing. Jiří Bobek','investor':'Ing. Jiří Bobek','project':'RD Lažánky','stage':'DSP'}


class ProjectDocumentTests(unittest.TestCase):
    def test_capital_c_selects_only_situation_drawings_without_duplicate_targets(self):
        expected = ["situace_prehled", "situace", "zastineni"]
        self.assertEqual(expand_drawing_targets(["C"]), expected)
        self.assertEqual(expand_drawing_targets(["situace", "C", "C"]),
                         ["situace", "situace_prehled", "zastineni"])
        self.assertEqual(expand_drawing_targets(["C", "ground"]), expected+["ground"])

    def test_other_targets_remain_case_sensitive_and_independent(self):
        for arguments in ([], ["ground"], ["aa", "bb"], ["kanal"], ["c"], ["A"]):
            with self.subTest(arguments=arguments):
                self.assertEqual(expand_drawing_targets(arguments), arguments)

    def test_document_ids_and_source_paths_are_unique(self):
        drawings=list(DRAWINGS.values())
        self.assertEqual(len(drawings),32)
        self.assertEqual(len({d.number for d in drawings}),len(drawings))
        self.assertEqual(len({d.pdf() for d in drawings}),len(drawings))
        for d in drawings:
            self.assertEqual(d.svg().parent,d.pdf().parent/'src')
            self.assertEqual(d.svg().stem,d.pdf().stem)
        self.assertEqual(document_path('ground').name,'D.1.1.2-02. Půdorys 1.NP.pdf')
        self.assertEqual(document_path('found').parent.name,'D.2. Základní stavebně konstrukční řešení')

    def test_new_title_block_numbers_are_separate_from_the_title(self):
        for key in ('ground','kanal_basement','situace_prehled','situace','zastineni'):
            d=DRAWINGS[key]
            root=ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg">'+title_block_svg(
                SETTINGS,filename=d.filename,scale='1:100',paper='A3',x=207,y=351)+'</svg>')
            texts=[e.text for e in root.findall('.//s:text',NS)]
            self.assertIn(d.number,texts)
            self.assertNotIn('—',texts)
            self.assertNotIn(d.filename[:-4],texts)

    def test_renaming_changes_labels_but_retains_geometry_and_title_block_position(self):
        d=DRAWINGS['ground']
        block=title_block_svg(SETTINGS,filename=Path(d.legacy_pdf).name,scale='1:100',paper='A4',x=207,y=141)
        original=('<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 297 210">'
                  '<g transform="translate(12,17)"><path id="house" d="M1 2L3 4"/></g>'
                  '<text class="drawing-title">D1.1.1. Půdorys 1.NP 1:100</text>'+block+'</svg>')
        renamed=ET.fromstring(update_sheet(original,d,SETTINGS))
        self.assertEqual(renamed.attrib,ET.fromstring(original).attrib)
        self.assertEqual(renamed.find('.//s:path[@id="house"]',NS).get('d'),'M1 2L3 4')
        blocks=renamed.findall('.//s:g[@class="drawing-title-block"]',NS)
        self.assertEqual(len(blocks),1)
        self.assertEqual(blocks[0].get('transform'),'translate(207, 141)')
        self.assertEqual(renamed.find('s:g',NS).get('transform'),'translate(12,17)')
        texts=' '.join(renamed.itertext())
        self.assertIn('D.1.1.2-02. Půdorys 1.NP 1:100',texts)
        self.assertNotIn('D1.1.1',texts)
        # Repeating the migration must not duplicate title blocks or rename again.
        again=update_sheet(ET.tostring(renamed,encoding='unicode'),d,SETTINGS)
        self.assertEqual(len(ET.fromstring(again).findall('.//s:g[@class="drawing-title-block"]',NS)),1)


if __name__=='__main__':
    unittest.main()
