from config import ROOT
import yaml


def test_actions_workflow_is_parseable_and_commands_are_strings():
    # BaseLoader preserves the YAML key "on" without YAML 1.1 boolean coercion.
    data=yaml.load((ROOT/'.github/workflows/tests.yml').read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
    assert {'push','pull_request'} <= set(data['on'])
    assert data['jobs']['tests']['strategy']['matrix']['os']==['ubuntu-latest','windows-latest','macos-latest']
    for job in data['jobs'].values():
        assert job['steps']
        for step in job['steps']:
            if 'run' in step:
                assert isinstance(step['run'],str)
    assert 'docker' in data['jobs']
