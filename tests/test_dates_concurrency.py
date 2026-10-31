from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from repository import BusinessError
from services.import_service import add_manual
from services.fact_service import build_snapshot, confirm_fact
from services import query_service as queries
from tests.conftest import confirmed
from tests.test_content import ready


def test_future_price_is_held_then_reminded_without_auto_confirm(repo, monkeypatch):
    p=confirmed(repo)
    cid=ready(repo,p)
    before=build_snapshot(repo,p)
    obs=add_manual(repo,p,'price_cent','14.00','retail','未来拟制价单','暂存','甲','2099-01-01')
    assert build_snapshot(repo,p)['snapshot_hash'] == before['snapshot_hash']
    assert queries.dated_candidates(repo,p)[0]['availability']=='future'
    import services.quality_service as quality
    import services.fact_service as facts
    import services.query_service as query
    for module in (quality,facts,query):
        monkeypatch.setattr(module,'today_iso',lambda:'2099-01-01')
    assert queries.dated_candidates(repo,p)[0]['availability']=='due'
    assert build_snapshot(repo,p)['missing']==['price_cent']
    old=repo.one("SELECT id FROM fact_revisions WHERE product_id=? AND field='price_cent' AND state='current'",(p,))['id']
    assert repo.one('SELECT state FROM content_revisions WHERE id=?',(cid,))['state']=='ready'
    confirm_fact(repo,p,obs,old,'甲','适用日期到达后核对')
    assert repo.one('SELECT state FROM content_revisions WHERE id=?',(cid,))['state']=='stale'


def test_two_writers_cannot_confirm_against_same_old_revision(repo):
    p=confirmed(repo)
    ready(repo,p)
    old=repo.one("SELECT id FROM fact_revisions WHERE product_id=? AND field='price_cent' AND state='current'",(p,))['id']
    observations=[add_manual(repo,p,'price_cent','14.00','retail','并发拟制证据','核对','甲') for _ in range(2)]
    barrier=Barrier(2)
    def writer(obs):
        barrier.wait(timeout=5)
        try:
            return ('ok', confirm_fact(repo,p,obs,old,'甲','并发确认'))
        except BusinessError as error:
            return ('error',error.code)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(writer,observations))
    assert sum(r[0]=='ok' for r in results)==1
    assert ('error','concurrent_change') in results
    assert len(repo.all("SELECT * FROM fact_revisions WHERE product_id=? AND field='price_cent' AND state='current'",(p,)))==1


def test_independent_write_connections_do_not_mix_transactions(repo):
    with ThreadPoolExecutor(max_workers=4) as executor:
        ids=list(executor.map(lambda i:repo.add_product(f'parallel-{i}','V1'),range(20)))
    assert len(set(ids))==20 and len(repo.products())==20
