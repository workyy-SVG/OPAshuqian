import pytest
from repository import BusinessError
from services.content_service import edit_content, submit_for_review, approve_content, export_content
from services.text_check_service import text_issues
from services.fact_service import build_snapshot
from tests.conftest import confirmed
from tests.test_content import ready
from tests.test_impact import change_price


def test_old_price_cannot_rebind_to_new_basis(repo):
    p = confirmed(repo)
    cid = ready(repo, p)
    old = repo.one('SELECT * FROM content_revisions WHERE id=?', (cid,))
    change_price(repo, p)
    with pytest.raises(BusinessError, match='14.00'):
        edit_content(repo, cid, old['title'], old['body'], '甲', '沿用', rebind=True)
    assert len(repo.all('SELECT * FROM content_revisions')) == 1
    new = edit_content(repo, cid, old['title'], old['body'].replace('12.00', '14.00'), '甲', '修改价格', rebind=True)
    submit_for_review(repo, new, '甲')


@pytest.mark.parametrize('stage', ['draft', 'review', 'ready'])
def test_each_gate_rechecks_explicit_facts_in_existing_rows(repo, stage):
    p = confirmed(repo)
    cid = ready(repo, p)
    row = repo.one('SELECT * FROM content_revisions WHERE id=?', (cid,))
    # Simulate a legacy row from before validation was introduced.
    with repo.connect(write=True) as db:
        db.execute('UPDATE content_revisions SET body=?,state=? WHERE id=?', (row['body'].replace('12.00', '99.00'), stage, cid))
    with pytest.raises(BusinessError, match='99.00'):
        if stage == 'draft':
            submit_for_review(repo, cid, '甲')
        elif stage == 'review':
            approve_content(repo, cid, '甲', row['snapshot_hash'], '误点通过')
        else:
            export_content(repo, cid, '甲')
    assert not repo.all('SELECT * FROM export_records')


def test_weight_currency_and_omitted_price(repo):
    p = confirmed(repo)
    snap = build_snapshot(repo, p)['snapshot']
    assert not text_issues('拟制辣椒酱', '净含量0.2kg，售价￥12.00', snap)
    assert text_issues('拟制辣椒酱', '净含量250克，售价12元', snap)
    no_price = build_snapshot(repo, p, include_price=False)['snapshot']
    assert text_issues('拟制辣椒酱', '净含量200克，售价12元', no_price)
