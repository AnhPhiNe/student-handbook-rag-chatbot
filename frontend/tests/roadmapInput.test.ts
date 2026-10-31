import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';

const require = createRequire(import.meta.url);
const { session, find, text } = require('./helpers/pageHarness.cjs');

test('empty next-term tab asks for current GPA and credits, not the graduation total', () => {
  const harness = session({ currentGpa: '', currentCredits: '', totalDegreeCredits: '' });
  const tree = harness.render('TargetGpaPage', { cohort: 'K49' });
  const mobile = find(tree, n => n.props.className === 'gpa-mobile-layout');
  const capsule = find(mobile, n => n.props.className === 'gpa-m-capsule empty');
  assert.match(text(capsule), /Nhập GPA tích lũy và tín chỉ/);
  assert.doesNotMatch(text(capsule), /toàn khóa|tốt nghiệp/);
});

function page(totalDegreeCredits = '') {
  const harness = session({ currentGpa: '3.56', currentCredits: '100', totalDegreeCredits });
  const render = () => harness.render('TargetGpaPage', { cohort: 'K49' });
  const result = () => find(render(), n => n.props.id === 'target-gpa-result');
  const hero = () => text(find(result(), n => n.props.className === 'gpa-d-hero-score'));
  const roadmap = () => find(render(), n => n.props.role === 'tab' && text(n) === 'Mục tiêu tốt nghiệp').props.onClick();
  const total = value => find(render(), n => n.props.id === 'total-degree-creds-input').props.onChange({ target: { value } });
  return { render, result, hero, roadmap, total };
}

test('roadmap waits for a real degree total instead of assuming 122', () => {
  const p = page();
  assert.notEqual(p.hero(), '--', 'term planning does not require the degree total');
  p.roadmap();
  assert.equal(p.hero(), '--');
  assert.match(text(p.result()), /Nhập tổng tín chỉ toàn khóa/);
  assert.doesNotMatch(text(p.result()), /122|3\.78/);
  const mobile = find(p.render(), n => n.props.className === 'gpa-mobile-layout');
  assert.equal(text(find(mobile, n => n.props.className === 'gpa-m-score-val')), '--');
});

test('entering a total computes the real plan; clearing it removes stale results', () => {
  const p = page();
  p.roadmap();
  p.total('135');
  assert.equal(p.hero(), '3.71');
  assert.match(text(p.result()), /35 TC/);
  p.total('');
  assert.equal(p.hero(), '--');
  assert.match(p.result().props.className, /status-empty/);
  assert.doesNotMatch(text(p.result()), /35 TC|3\.71/);
});

test('invalid persisted totals cannot produce a graduation forecast', () => {
  for (const value of ['0', '-1', '1.5', 'Infinity', 'abc']) {
    const p = page(value);
    p.roadmap();
    assert.equal(p.hero(), '--', value);
    assert.match(text(p.result()), /Tổng tín chỉ phải là số nguyên dương/);
  }
});
