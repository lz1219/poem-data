"""Separate verified source event numbers from an existing structured unit.

Preview creates a full backup and checked plan. Apply requires that backup's
SHA-256; verify is read-only. This does not infer missing events or numbering.
"""
import argparse, copy, gzip, hashlib, json, os, re, time
from pathlib import Path
from backfill_shiji import canonical, copy_rows, digest, require

PREFIX = re.compile(r'^(\d+)\u3000')


def make_plan(snapshot):
    unit = snapshot['unit']; rows = copy.deepcopy(snapshot['rows']); groups = {}; count = notes = 0
    require(snapshot['unitOrigin']['metadata']['revisionId'] == 2489405 and unit['id'] == 2080,
            'Only the reviewed fixed-source unit is supported')
    require(unit['body'] == '\n\n'.join(r['paragraph']['body'] for r in rows), 'Unit/paragraph mismatch')
    for row in rows:
        p, meta = row['paragraph'], row['origin']['metadata']
        match = PREFIX.match(p['body'])
        if not match:
            require(not meta.get('eventNumber'), 'Unmatched event metadata')
            continue
        require(meta.get('eventNumber') == match[1] and meta.get('kind') == 'paragraph', 'Number does not match source structure')
        spans = meta.get('spans')
        require(spans == [{'kind':'source-text','start':0,'end':len(p['body'])}], 'Unsupported source span')
        length = match.end(); oldbody = p['body']; p['body'] = oldbody[length:]
        require(p['body'], 'Empty text after number separation')
        for note in meta.get('annotations',[]):
            require(type(note['anchor']) is int and length <= note['anchor'] <= len(oldbody), 'Cannot move source note anchor')
            note['anchor'] -= length; notes += 1
        meta['spans'] = [{'kind':'source-text','start':0,'end':len(p['body'])}]
        meta['sourceEventPrefix'] = match[0]
        path = tuple((v['level'],v['title']) for v in meta.get('headingPath',[]))
        groups.setdefault(path,[]).append(int(match[1])); count += 1
    require(count == 75 and notes == 26, 'Unexpected reviewed scope')
    text_offset=0
    for row in rows:
        meta=row['origin']['metadata'];meta['textStart']=text_offset
        text_offset+=len(row['paragraph']['body']);meta['textEnd']=text_offset;text_offset+=2
    newbody='\n\n'.join(r['paragraph']['body'] for r in rows)
    simplified_blocks=unit['body_simplified'].split('\n\n')
    require(len(simplified_blocks)==len(rows),'Simplified block count mismatch')
    for index, original in enumerate(snapshot['rows']):
        expected=PREFIX.match(original['paragraph']['body'])
        actual=PREFIX.match(simplified_blocks[index])
        require((actual[0] if actual else None)==(expected[0] if expected else None),'Simplified source prefix mismatch')
        if actual:simplified_blocks[index]=simplified_blocks[index][actual.end():]
    simplified='\n\n'.join(simplified_blocks)
    gaps=[]
    for path,numbers in groups.items():
        missing=sorted(set(range(1,max(numbers)+1))-set(numbers))
        if missing:gaps.append({'sourceHeadingPath':[{'level':k,'title':v} for k,v in path],
                                'observed':numbers,'missing':missing,'status':'source-number-gap-unresolved'})
    return {'rows':rows,'body':newbody,'bodySimplified':simplified,
            'sha256':hashlib.sha256(newbody.encode()).hexdigest(),'separated':count,'notesMoved':notes,'gaps':gaps}


def read_snapshot(conn):
    unit=conn.execute('SELECT to_jsonb(t) FROM text_unit t WHERE id=2080').fetchone()[0]
    unit_origin=conn.execute('SELECT to_jsonb(o) FROM corpus_unit_origin o WHERE unit_id=2080').fetchone()[0]
    rows=[{'paragraph':p,'origin':o} for p,o in conn.execute('SELECT to_jsonb(p),to_jsonb(o) FROM paragraph p JOIN corpus_paragraph_origin o ON o.paragraph_id=p.id WHERE p.unit_id=2080 ORDER BY p.seq')]
    require(len(rows)==125 and conn.execute('SELECT count(*) FROM paragraph WHERE unit_id=2080').fetchone()[0]==len(rows),'Missing source origins')
    batch=conn.execute('SELECT to_jsonb(b) FROM corpus_ingest_batch b WHERE batch_id=%s',(unit_origin['batch_id'],)).fetchone()[0]
    return {'unit':unit,'unitOrigin':unit_origin,'rows':rows,'oldBatch':batch}


def guard_references(conn):
    from psycopg import sql
    known={('paragraph','unit_id','text_unit'),('corpus_unit_origin','unit_id','text_unit'),
           ('corpus_paragraph_origin','paragraph_id','paragraph'),('evidence','unit_id','text_unit'),
           ('evidence','paragraph_id','paragraph'),('person_source','unit_id','text_unit'),('text_variant','unit_id','text_unit')}
    refs=conn.execute("""SELECT n.nspname,t.relname,a.attname,target.relname,cardinality(k.conkey)
        FROM pg_constraint k JOIN pg_class t ON t.oid=k.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN pg_class target ON target.oid=k.confrelid JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.conkey[1]
        WHERE k.contype='f' AND k.confrelid IN('public.text_unit'::regclass,'public.paragraph'::regclass)""").fetchall()
    for schema,table,col,target,width in refs:
        require(schema=='public' and width==1 and (table,col,target) in known,'Unknown reference requires review')
        if table in ('paragraph','corpus_unit_origin','corpus_paragraph_origin'):continue
        sub='SELECT id FROM text_unit WHERE id=2080' if target=='text_unit' else 'SELECT id FROM paragraph WHERE unit_id=2080'
        q=sql.SQL('SELECT count(*) FROM public.{} WHERE {} IN ('+sub+')').format(sql.Identifier(table),sql.Identifier(col))
        require(conn.execute(q).fetchone()[0]==0,'Existing reference requires migration: '+table)


def apply(conn,snapshot,plan,backup_sha):
    from psycopg.types.json import Jsonb
    require(make_plan(snapshot)==plan,'Backup plan mismatch')
    batch_id='source-numbers-'+digest({'oldBatch':snapshot['oldBatch']['batch_id'],'newSha':plan['sha256']})
    start=time.monotonic()
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout='3s'");conn.execute("SET LOCAL statement_timeout='8s'")
        if conn.info.server_version>=170000:conn.execute("SET LOCAL transaction_timeout='15s'")
        require(conn.execute('SELECT pg_try_advisory_xact_lock(730015,80)').fetchone()[0],'Book busy')
        existing=conn.execute("SELECT state FROM corpus_ingest_batch WHERE batch_id=%s",(batch_id,)).fetchone()
        if existing:
            require(existing[0]=='applied','Previously rolled-back batch requires explicit review')
            return {'operation':'already-applied; no writes','batchId':batch_id}
        conn.execute('SELECT id FROM text_unit WHERE id=2080 FOR UPDATE').fetchall()
        conn.execute('SELECT id FROM paragraph WHERE unit_id=2080 ORDER BY id FOR UPDATE').fetchall()
        conn.execute('SELECT paragraph_id FROM corpus_paragraph_origin WHERE paragraph_id IN(SELECT id FROM paragraph WHERE unit_id=2080) ORDER BY paragraph_id FOR UPDATE').fetchall()
        conn.execute('SELECT unit_id FROM corpus_unit_origin WHERE unit_id=2080 FOR UPDATE').fetchall()
        require(read_snapshot(conn)==snapshot,'Data changed since preview')
        guard_references(conn)
        manifest=copy.deepcopy(snapshot['oldBatch']['manifest']);manifest.pop('unitDigests',None)
        manifest['sourceNumberSeparation']={'parentBatchId':snapshot['oldBatch']['batch_id'],'oldUnitSha256':snapshot['unit']['sha256'],
            'newUnitSha256':plan['sha256'],'separated':plan['separated'],'sourceNumberGaps':plan['gaps'],'backupSha256':backup_sha}
        result={'unitId':2080,'paragraphIds':[r['paragraph']['id'] for r in plan['rows']],'sourceNumberGaps':plan['gaps'],'backupSha256':backup_sha}
        conn.execute("INSERT INTO corpus_ingest_batch(batch_id,book_id,edition_id,state,manifest,result) VALUES(%s,80,%s,'applied',%s,%s)",
                     (batch_id,snapshot['unitOrigin']['edition_id'],Jsonb(manifest),Jsonb(result)))
        conn.execute('UPDATE text_unit SET body=%s,body_simplified=%s,sha256=%s WHERE id=2080',(plan['body'],plan['bodySimplified'],plan['sha256']))
        conn.execute('CREATE TEMP TABLE source_number_update(id integer PRIMARY KEY,body text,metadata jsonb) ON COMMIT DROP')
        copy_rows(conn,'COPY source_number_update(id,body,metadata) FROM STDIN',((r['paragraph']['id'],r['paragraph']['body'],Jsonb(r['origin']['metadata'])) for r in plan['rows']))
        conn.execute('UPDATE paragraph p SET body=s.body FROM source_number_update s WHERE p.id=s.id AND p.body IS DISTINCT FROM s.body')
        conn.execute('UPDATE corpus_paragraph_origin o SET metadata=s.metadata,batch_id=%s FROM source_number_update s WHERE o.paragraph_id=s.id',(batch_id,))
        conn.execute('UPDATE corpus_unit_origin SET batch_id=%s WHERE unit_id=2080',(batch_id,))
    return {'operation':'applied','batchId':batch_id,'transactionSeconds':round(time.monotonic()-start,4)}


def verify(conn,snapshot,plan):
    unit=conn.execute('SELECT body,body_simplified,sha256 FROM text_unit WHERE id=2080').fetchone()
    require(unit==(plan['body'],plan['bodySimplified'],plan['sha256']),'Unit differs')
    batch_id='source-numbers-'+digest({'oldBatch':snapshot['oldBatch']['batch_id'],'newSha':plan['sha256']})
    rows=conn.execute('SELECT p.id,p.seq,p.body,o.metadata,o.batch_id FROM paragraph p LEFT JOIN corpus_paragraph_origin o ON o.paragraph_id=p.id WHERE p.unit_id=2080 ORDER BY p.seq').fetchall()
    require(len(rows)==len(plan['rows']),'Paragraph count differs')
    for actual,expected in zip(rows,plan['rows']):
        p=expected['paragraph'];require(actual==(p['id'],p['seq'],p['body'],expected['origin']['metadata'],batch_id),'Paragraph or source metadata differs')
    origin=conn.execute('SELECT batch_id,edition_id,metadata FROM corpus_unit_origin WHERE unit_id=2080').fetchone()
    require(origin==(batch_id,snapshot['unitOrigin']['edition_id'],snapshot['unitOrigin']['metadata']),'Unit origin differs')
    require(conn.execute('SELECT to_jsonb(b) FROM corpus_ingest_batch b WHERE batch_id=%s',(snapshot['oldBatch']['batch_id'],)).fetchone()[0]==snapshot['oldBatch'],'Previous batch changed')
    return {'paragraphs':len(rows),'separated':plan['separated'],'sourceNotesRetained':sum(len(r[3].get('annotations',[])) for r in rows),'gaps':plan['gaps'],'newUnitSha256':plan['sha256']}


def main():
    import psycopg
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=('preview','apply','verify'),nargs='?',default='preview')
    parser.add_argument('--backup',required=True,type=Path);parser.add_argument('--backup-sha');parser.add_argument('--output',type=Path);args=parser.parse_args()
    dsn=os.environ.get('CORPUS_DSN');require(bool(dsn),'Use protected CORPUS_DSN')
    if args.operation=='preview':
        with psycopg.connect(dsn,autocommit=True,options='-c statement_timeout=10000') as conn:
            with conn.transaction():
                conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                snapshot=read_snapshot(conn);guard_references(conn);plan=make_plan(snapshot)
        raw=gzip.compress(canonical({'snapshot':snapshot,'plan':plan}),compresslevel=1)
        args.backup.parent.mkdir(parents=True,exist_ok=True)
        with args.backup.open('xb') as stream:stream.write(raw)
        require(json.loads(gzip.decompress(args.backup.read_bytes()))==json.loads(canonical({'snapshot':snapshot,'plan':plan})),'Backup mismatch')
        result={'operation':'preview','backupSha256':hashlib.sha256(raw).hexdigest(),'backupBytes':len(raw),'separated':plan['separated'],'notesMoved':plan['notesMoved'],'gaps':plan['gaps']}
    else:
        raw=args.backup.read_bytes();require(hashlib.sha256(raw).hexdigest()==args.backup_sha,'Backup SHA mismatch')
        data=json.loads(gzip.decompress(raw));snapshot,plan=data['snapshot'],data['plan'];result={}
        if args.operation=='apply':
            with psycopg.connect(dsn,autocommit=True,application_name='separate-source-numbers') as conn:result=apply(conn,snapshot,plan,args.backup_sha)
        with psycopg.connect(dsn,autocommit=True,options='-c default_transaction_read_only=on -c statement_timeout=10000') as conn:result.update(verify(conn,snapshot,plan))
    if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
