import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from research import cached_response,save_object
from raw_ingest import sha


class CaptureCacheTests(unittest.TestCase):
    def test_old_capture_survives_mutable_url_cache_refresh(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder);url='https://example.org/export';old=b'old revision';new=b'new revision'
            digest=save_object(cache,old);(cache/sha(url.encode())).write_bytes(new)
            self.assertEqual(cached_response(cache,url,digest),old)
            save_object(cache,new)
            self.assertEqual(cached_response(cache,url,sha(new)),new)

    def test_concurrent_capture_cannot_publish_partial_or_overwrite_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder);raw=b'capture'*10000
            with ThreadPoolExecutor(max_workers=4) as pool: result=list(pool.map(lambda _:save_object(cache,raw),range(8)))
            self.assertEqual(len(set(result)),1)
            self.assertEqual((cache/'objects'/result[0]).read_bytes(),raw)
            self.assertEqual(len(list((cache/'objects').iterdir())),1)

    def test_corrupt_object_is_rejected_and_never_silently_repaired(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder);key=save_object(cache,b'original');target=cache/'objects'/key;target.write_bytes(b'bad')
            with self.assertRaises(ValueError): cached_response(cache,'https://example.org',key)
            with self.assertRaises(ValueError): save_object(cache,b'original')
            self.assertEqual(target.read_bytes(),b'bad')


if __name__=='__main__':unittest.main()
