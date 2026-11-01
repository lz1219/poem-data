"""地方志卷题冲突与原条边界不被默默归一。"""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('guizhou',Path(__file__).with_name('organize-guizhou.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class GazetteerTests(unittest.TestCase):
    def test_conflicting_headings_keep_original_bytes(self):
        raw=('\ufeff#+PROPERTY: JUAN 卷二十八\n<pb:book-1a>¶\n　貴州通志卷三十八¶\n'
             '　正文¶\n<pb:book-36b>¶\n　貴州通志卷二十八¶\n').encode()
        rows=module.headings(raw)
        self.assertEqual([r['volume'] for r in rows],[38,28])
        self.assertEqual([r['sourcePageMarker'] for r in rows],['book-1a','book-36b'])
        for r in rows:self.assertEqual(raw[r['startByte']:r['endByte']].decode(),r['header'])

    def test_excerpt_requires_real_following_entry_boundary(self):
        raw='\ufeff<pb:b>¶\n　陽明洞(舊名東洞/游息其中)¶\n　石天洞(另條)'.encode()
        found=module.excerpt(raw,'陽明洞(','石天洞')
        self.assertEqual(raw[found['startByte']:found['endByte']].decode(),found['quote'])
        self.assertNotIn('石天洞',found['quote'])
        self.assertEqual(found['page'],'b')
        with self.assertRaises(ValueError):module.excerpt(raw,'陽明洞(','不存在')


if __name__=='__main__':unittest.main()
