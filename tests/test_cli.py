import json
import subprocess
import sys


def test_cli_demo_verify_counterfactual(tmp_path):
    db = tmp_path/'test.db'
    report = tmp_path/'result.json'
    def call(*args):
        completed = subprocess.run(
            [sys.executable, '-m', 'causal_lab.cli', '--db', str(db), *args],
            capture_output=True, text=True, check=True
        )
        return json.loads(completed.stdout)
    out = call('demo','--report',str(report))
    assert out['original_outcome'] == 'APPROVE'
    assert out['alternate_outcome'] == 'BLOCK'
    assert call('verify')['verified']
    assert call('counterfactual')['side_effects_executed'] == 0
    assert json.loads(report.read_text())['proof']['verified']


def test_local_benchmark(tmp_path):
    db = tmp_path/'bench.db'
    report = tmp_path/'bench.json'
    out = subprocess.run([sys.executable,'-m','causal_lab.cli', '--db', str(db),
        'benchmark','--accounts','10','--report',str(report)],
        capture_output=True,text=True,check=True)
    assert json.loads(out.stdout)['backend'] == 'local_sqlite_only'
    assert json.loads(report.read_text())['accounts'] == 10
