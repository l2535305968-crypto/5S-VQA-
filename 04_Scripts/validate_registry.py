#!/usr/bin/env python3
"""Open-style registry validator; stdlib checks, optional full jsonschema validation.

The schema intentionally supports extensions / previously unknown visual media.
This validator checks syntax and metadata, NOT whether art is aesthetically good.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED = {
    'profile_id','display_name','version','status','scope','description',
    'intent','medium','visual_rules','intentional_effects','defect_rules',
    'inspection','acceptance','compatibility','references','change_history','extensions'
}
REQUIRED_AXES = {'composition','geometry','palette','lighting','surface','edges','detail_density'}
Q_VALUES = {'Q1','Q2','Q3','Q4','Q5','Q6','Q7'}
P_VALUES = {'P0','P1','P2','P3'}

def read_json(p):
    with p.open(encoding='utf-8') as f:
        return json.load(f)

def validate_one(profile, location):
    errs=[]
    missing=REQUIRED-set(profile)
    if missing: errs.append(f'{location}: missing fields {sorted(missing)}')
    pid=profile.get('profile_id')
    if not isinstance(pid,str) or not re.fullmatch(r'[a-z][a-z0-9-]{2,63}',pid):
        errs.append(f'{location}: invalid profile_id')
    version=profile.get('version')
    if not isinstance(version,str) or not re.fullmatch(r'\d+\.\d+\.\d+',version):
        errs.append(f'{location}: invalid version')
    if profile.get('status') not in {'draft','approved','deprecated'}:
        errs.append(f'{location}: invalid status')
    if profile.get('scope') not in {'style','medium','project'}:
        errs.append(f'{location}: invalid scope')
    if not isinstance(profile.get('visual_rules'),dict) or not REQUIRED_AXES.issubset(profile['visual_rules']):
        errs.append(f'{location}: missing visual axes')
    if not isinstance(profile.get('acceptance'),dict):
        errs.append(f'{location}: missing acceptance object')
    else:
        score=profile['acceptance'].get('minimum_total_score')
        if type(score)!=int or not 0<=score<=100:
            errs.append(f'{location}: minimum_total_score must be 0..100 integer')
        na=profile['acceptance'].get('non_applicable_q')
        if not isinstance(na,list) or not set(na).issubset(Q_VALUES):
            errs.append(f'{location}: invalid non_applicable_q')
    for defect in profile.get('defect_rules',[]) if isinstance(profile.get('defect_rules'),list) else []:
        if not isinstance(defect,dict) or not {'id','symptom','severity','inspection'}.issubset(defect):
            errs.append(f'{location}: incomplete defect rule')
        elif defect['severity'] not in P_VALUES:
            errs.append(f'{location}: invalid defect severity {defect["severity"]}')
    return errs


def main(argv=None):
    parser=argparse.ArgumentParser(description='Validate extensible VQA style registry')
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent/'02_Style_Registry')
    parser.add_argument('--strict',action='store_true',help='Require jsonschema package to validate against full schema')
    args=parser.parse_args(argv)
    index_path=args.root/'registry.json'
    schema_path=args.root/'profile.schema.json'
    try:
        index=read_json(index_path)
        schema=read_json(schema_path)
    except (OSError,json.JSONDecodeError) as exc:
        print(f'INVALID: {exc}',file=sys.stderr)
        return 2
    errors=[]
    ids=set()
    entries=index.get('entries')
    if not isinstance(entries,list):
        print('INVALID: registry.entries must be an array',file=sys.stderr)
        return 2
    profiles=[]
    for item in entries:
        if not isinstance(item,dict) or not {'profile_id','path','version','status'}.issubset(item):
            errors.append('Invalid registry entry')
            continue
        rel=Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts:
            errors.append(f"Unsafe relative path: {item['path']}")
            continue
        p=args.root/rel
        try:
            profile=read_json(p)
        except (OSError,json.JSONDecodeError) as exc:
            errors.append(f'{p}: {exc}')
            continue
        errors.extend(validate_one(profile,str(rel)))
        if profile.get('profile_id')!=item['profile_id']:
            errors.append(f"{rel}: ID != registry index")
        if profile.get('version')!=item['version'] or profile.get('status')!=item['status']:
            errors.append(f'{rel}: version/status differs from index')
        if profile.get('status')=='draft':
            errors.append(f'{rel}: draft cannot be registered as official')
        if item['profile_id'] in ids:
            errors.append(f"Duplicate ID: {item['profile_id']}")
        ids.add(item['profile_id'])
        profiles.append((rel,profile))
    try:
        import jsonschema
    except ImportError:
        if args.strict:
            errors.append('jsonschema not installed; cannot perform --strict schema checks')
        else:
            print('INFO: jsonschema optional dependency unavailable, stdlib checks performed.')
    else:
        validator=jsonschema.Draft202012Validator(schema)
        for rel,profile in profiles:
            for err in validator.iter_errors(profile):
                errors.append(f'{rel}: schema {"/".join(map(str,err.path))}: {err.message}')
    if errors:
        for error in errors:print('ERROR:',error,file=sys.stderr)
        print(f'FAIL: {len(errors)} problems',file=sys.stderr)
        return 2
    print(f'PASS: {len(profiles)} registered profiles; open-ended fields retained; templates not promoted automatically.')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
