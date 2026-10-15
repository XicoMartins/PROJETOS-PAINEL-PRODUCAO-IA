"""Exact, project-scoped accumulated report snapshots (JSON-safe)."""
import json
from datetime import date, datetime
from dataclasses import asdict
from decimal import Decimal
from weekly_control import build_weekly_control, ComponentRequirement, normalize_text, project_key, component_key

def decimal_string(value):
    if value is None: return None
    number=Decimal(value)
    text=format(number, 'f')
    return '0' if number == 0 else (text.rstrip('0').rstrip('.') if '.' in text else text)

def complete_requirements(source):
    requirements=list(source.requirements)
    known={normalize_text(item.source_component_key) for item in requirements}
    used={item.display_order for item in requirements}
    for key in source.detected_component_keys:
        if normalize_text(key) in known: continue
        order=0
        while order in used: order+=1
        used.add(order); known.add(normalize_text(key))
        requirements.append(ComponentRequirement(key,key,None,order,True))
    return tuple(sorted(requirements,key=lambda item:item.display_order))

def snapshot(identity, source):
    requirements=complete_requirements(source)
    order={normalize_text(item.source_component_key):item.display_order for item in requirements}
    control=build_weekly_control(source.previous_target,source.current_target,requirements,source.entries)
    rows={}
    for kind,items in (('component',control.components),('paint',control.paint_rows)):
        for row in items:
            value={key:decimal_string(item) if isinstance(item,Decimal) else item for key,item in asdict(row).items()}
            value['kind']=kind
            value['display_order']=order.get(row.component_key)
            def json_value(item):
                if isinstance(item,Decimal): return decimal_string(item)
                if isinstance(item,(datetime,date)): return item.isoformat()
                if item is None or isinstance(item,(str,int,float,bool)): return item
                return str(item)
            value['source_entries']=sorted(json.dumps(entry,sort_keys=True,default=json_value,ensure_ascii=False) for entry in source.source_entries if component_key(entry.get('processo'))==row.component_key)
            value['entries']=sorted([[entry.movement,decimal_string(entry.quantity),entry.occurred_at.isoformat()] for entry in source.entries if normalize_text(entry.component_key)==row.component_key])
            rows[kind+':'+row.component_key]=value
    return {'project_key':project_key(identity),'identity':asdict(identity),'targets':[source.previous_target,source.current_target], 'rows':rows}

def changes(current, previous):
    old=previous['rows'] if previous else {}
    result=[]
    for key in dict.fromkeys([*current['rows'],*old]):
        now=current['rows'].get(key); before=old.get(key)
        target_changed = (
            previous is not None
            and current['targets'] != previous['targets']
            and (now or before)['kind'] == 'component'
        )
        if previous is not None and now == before and not target_changed:
            continue
        deltas={}
        for field in ('total_remessa','total_retorno','painting_balance'):
            a=before.get(field) if before else '0'; b=now.get(field) if now else '0'
            deltas[field]=decimal_string(Decimal(b)-Decimal(a)) if a is not None and b is not None else None
        result.append({'key':key,'previous':before,'current':now,'removed':now is None,'deltas':deltas})
    return result

ALL_PROJECTS='__all__'
def select_projects(projects, selected):
    by_key={project.key:project for project in projects}
    if ALL_PROJECTS in selected:
        return tuple(projects)
    return tuple(by_key[key] for key in dict.fromkeys(selected) if key in by_key)
