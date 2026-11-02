"""Read-only progress summaries; never confirm or generate automatically."""
from typing import Any
from repository import Repository
from services import query_service as queries
from services.quality_service import detect_issues


def overview(repo: Repository, product_id: int | None) -> dict[str, Any]:
    if not product_id:
        return {'confirmed':0,'conflicts':0,'pending':0,'latest':None,'stage':'未录入','steps':[False]*4,'distribution':[]}
    facts = queries.current_facts(repo, product_id)
    issues = detect_issues(repo, product_id)
    contents = queries.content_history(repo, product_id, False)
    required = sum(any(f['field']==field and f['context']=='general' for f in facts)
                   for field in ('product_name','net_weight_g'))
    conflicts = [i for i in issues if i['type']=='conflict']
    pending = [i for i in issues if 'observations' in i]
    events = queries.change_history(repo, product_id)
    latest = contents[0]['state'] if contents else None
    has_sources = bool(repo.one("SELECT 1 FROM observations WHERE product_id=? AND state!='error' LIMIT 1", (product_id,)))
    ready = required == 2 and not conflicts
    stage = ('可下载' if any(c['state']=='ready' for c in contents) else '待审核' if contents else
             '可生成' if ready else '缺资料' if required < 2 else '已收集待确认' if has_sources else '未录入')
    return {'confirmed':required,'conflicts':len(conflicts), 'pending':len(pending), 'latest':latest,'stage':stage,
            'steps':[has_sources,ready,any(c['state']=='ready' for c in contents),
                     bool(events) and bool(contents) and all(c['state']=='ready' for c in contents)],
            'distribution':[{'field':i['field'],'count':len({o['normalized'] for o in i['observations']})}
                            for i in conflicts]}
