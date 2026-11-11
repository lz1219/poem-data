"""把当前清单引用的原始HTTP响应迁至内容寻址缓存，兼容旧URL缓存。"""
import argparse
from pathlib import Path
from research import ROOT,save_object
from raw_ingest import input_bundle


def main(cache):
    bundle=input_bundle(cache=cache)
    keys={s[3] for s in bundle['snapshots']}
    roles={'source-response','image-original','image-preview','catalog','catalog-api-response','branch-api-response'}
    keys.update(a[2] for a in bundle['assets'] if a[1] in roles)
    for key in sorted(keys):
        if save_object(cache,bundle['blobs'][key])!=key: raise ValueError('原件身份不一致')
    print('已按内容哈希封存原始响应 '+str(len(keys))+' 份；不修改输入清单或数据库。',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,default=ROOT.parent/'.local/research-cache')
    main(p.parse_args().cache)
