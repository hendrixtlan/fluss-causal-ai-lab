import sqlite3
import pytest
from causal_lab.model import Event, utc_stamp
from causal_lab.ledger import Ledger, DuplicateEventError
from causal_lab.engine import DecisionEngine, CausalGapError, Policy
from causal_lab.scenario import (seed, ACCOUNT, DECISION_ID, VALID_AT,
                                 ORIGINAL_KNOWLEDGE, LATER_KNOWLEDGE)


def test_bank_late_arrival_and_proof(tmp_path):
    with Ledger(tmp_path / 'a.db') as ledger:
        result = seed(ledger)
        assert result['decision']['result']['outcome'] == 'APPROVE'
        assert result['proof']['verified'] is True
        assert result['counterfactual']['outcome_changed'] is True
        assert result['counterfactual']['alternate']['outcome'] == 'BLOCK'
        assert result['counterfactual']['newly_known_events'] == ['signal-001']
        assert result['counterfactual']['side_effects_executed'] == 0
        assert ledger.as_of(ACCOUNT, VALID_AT, ORIGINAL_KNOWLEDGE)[-1].event_id == 'tx-001'


def test_replay_is_stable_after_reopen(tmp_path):
    path = tmp_path / 'ledger.db'
    with Ledger(path) as l:
        seed(l)
        digest = l.decision(DECISION_ID)['decision_hash']
    with Ledger(path) as l:
        assert l.decision(DECISION_ID)['decision_hash'] == digest
        assert DecisionEngine(l).verify(DECISION_ID)['verified']


def test_append_only_tables(tmp_path):
    with Ledger(tmp_path / 'immut.db') as ledger:
        seed(ledger)
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            ledger.db.execute("DELETE FROM events")
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            ledger.db.execute("UPDATE decisions SET account_id='evil'")


def test_idempotent_duplicate_is_explicitly_rejected():
    with Ledger() as ledger:
        event = Event('a', 'acct', 'profile', '2026-10-14T08:00:00Z',
                      '2026-10-14T08:00:00Z', {'risk_score': 5})
        ledger.append(event)
        with pytest.raises(DuplicateEventError):
            ledger.append(event)
        with pytest.raises(DuplicateEventError):
            ledger.append(Event('a', 'acct', 'profile', event.valid_at,
                                event.observed_at, {'risk_score': 99}))


def test_as_of_valid_and_knowledge_filters_are_independent():
    with Ledger() as ledger:
        ledger.append(Event('future-early', 'acct', 'risk_signal',
                            '2026-10-15T10:00:00Z', '2026-10-14T08:00:00Z',
                            {'risk_score': 100}))
        ledger.append(Event('past-late', 'acct', 'profile',
                            '2026-10-13T08:00:00Z', '2026-10-15T08:00:00Z',
                            {'risk_score': 20}))
        assert ledger.as_of('acct', '2026-10-14T09:00:00Z',
                            '2026-10-14T09:00:00Z') == []
        assert [e.event_id for e in ledger.as_of('acct','2026-10-16T09:00:00Z',
                       '2026-10-14T09:00:00Z')] == ['future-early']


def test_causal_gap_detected_and_not_certified():
    with Ledger() as ledger:
        ledger.append(Event('child', 'acct', 'transaction', '2026-10-14T09:00:00Z',
                            '2026-10-14T09:00:00Z', {'amount_mxn': 100},
                            parents=('unknown-parent',)))
        engine = DecisionEngine(ledger)
        with pytest.raises(CausalGapError):
            engine.decide('d', 'acct', '2026-10-14T10:00:00Z',
                          '2026-10-14T10:00:00Z')
        engine.decide('d', 'acct', '2026-10-14T10:00:00Z',
                      '2026-10-14T10:00:00Z', strict_causality=False)
        verification = engine.verify('d')
        assert not verification['verified']
        assert not verification['checks']['causal_consistency']


def test_correction_supersedes_original_signal():
    with Ledger() as ledger:
        seed(ledger)
        ledger.append(Event('correct-001', ACCOUNT, 'risk_correction',
                            '2026-10-14T10:30:00Z', '2026-10-14T10:38:00Z',
                            {'risk_score': 20, 'supersedes': 'signal-001'},
                            source='external_risk_feed'))
        engine = DecisionEngine(ledger)
        assert engine.counterfactual(DECISION_ID,'2026-10-14T10:36:00Z')[
            'alternate']['outcome'] == 'BLOCK'
        after = engine.counterfactual(DECISION_ID,'2026-10-14T10:39:00Z')
        assert after['alternate']['outcome'] == 'APPROVE'
        assert engine.verify(DECISION_ID)['verified']


def test_tampered_policy_refuses_old_proof():
    with Ledger() as ledger:
        seed(ledger)
        assert not DecisionEngine(ledger,Policy(version='risk-v2')) .verify(DECISION_ID)['verified']


def test_invalid_times_and_payloads():
    with pytest.raises(ValueError, match='offset'):
        utc_stamp('2026-10-14T10:00:00')
    with pytest.raises(ValueError, match='risk_score'):
        Event('x','acc','profile','2026-10-14T10:00:00Z','2026-10-14T10:00:00Z',
              {'risk_score': 101})


def test_offsets_are_explicitly_local_not_fluss():
    with Ledger() as ledger:
        seed(ledger)
        m = ledger.decision(DECISION_ID)['manifest']
        assert 'local_sequence_high_watermarks' in m
        assert 'external_risk_feed' not in m['local_sequence_high_watermarks']


def test_no_cross_account_leakage():
    with Ledger() as ledger:
        seed(ledger)
        ledger.append(Event('other', 'other-account', 'risk_signal',
                            '2026-10-14T10:00:00Z', '2026-10-14T10:00:00Z',
                            {'risk_score': 100}))
        assert DecisionEngine(ledger).verify(DECISION_ID)['verified']
        assert DecisionEngine(ledger).counterfactual(DECISION_ID,LATER_KNOWLEDGE)[
            'alternate']['risk_score'] == 95


def test_original_decision_still_verified_when_late_data_arrives():
    with Ledger() as ledger:
        seed(ledger)
        ledger.append(Event('new-signal', ACCOUNT, 'risk_signal',
                            '2026-10-14T10:31:00Z', '2026-10-14T10:40:00Z',
                            {'risk_score': 100}))
        assert DecisionEngine(ledger).verify(DECISION_ID)['verified']


def test_no_backward_counterfactual():
    with Ledger() as ledger:
        seed(ledger)
        with pytest.raises(ValueError, match='precede'):
            DecisionEngine(ledger).counterfactual(DECISION_ID,'2026-10-14T10:00:00Z')
