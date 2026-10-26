import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { FACULTIES, OFFICES } from '../src/data/directory.ts';
import { contactText, findHighlight, foldText, searchUnits, telHref, unitsForTask } from '../src/utils/directory.ts';

const names = (query: string) => searchUnits(OFFICES, query).map((unit) => unit.name);

describe('foldText', () => {
  it('drops diacritics and maps đ to d', () => {
    assert.equal(foldText('Đăng ký học phần'), 'dang ky hoc phan');
  });
});

describe('searchUnits', () => {
  it('finds the exam office for "phúc khảo"', () => {
    assert.ok(names('phúc khảo').includes('Phòng Khảo thí và Đảm bảo chất lượng'));
  });
  it('works without diacritics', () => {
    assert.ok(names('hoc phi').includes('Phòng Kế hoạch – Tài chính'));
  });
  it('finds the dormitory for "ktx" and IT for "wifi"', () => {
    assert.ok(names('ktx').includes('Ký túc xá'));
    assert.ok(names('wifi').includes('Phòng Công nghệ Thông tin'));
  });
  it('matches a keyword inside a longer question', () => {
    assert.ok(names('tôi muốn phúc khảo bài thi').includes('Phòng Khảo thí và Đảm bảo chất lượng'));
  });
  it('returns everything for an empty query', () => {
    assert.equal(searchUnits(OFFICES, '  ').length, OFFICES.length);
  });
  it('returns nothing for gibberish', () => {
    assert.deepEqual(names('zzzzqx'), []);
  });
});

describe('unitsForTask', () => {
  it('matches on the unit name', () => {
    assert.deepEqual(unitsForTask(OFFICES, 'Ký túc xá').map((unit) => unit.name), ['Ký túc xá']);
  });
});

describe('telHref', () => {
  it('dials the main number and then the extension', () => {
    assert.equal(telHref('(028) 38352020', '127'), 'tel:02838352020,127');
  });
  it('omits the extension when there is none', () => {
    assert.equal(telHref('(028) 38352020'), 'tel:02838352020');
  });
});

describe('contactText', () => {
  it('lists the phone, extensions and emails', () => {
    const text = contactText({ ...OFFICES[0], phones: ['(028) 38352020'], ext: ['141', '142'], emails: ['a@hcmue.edu.vn'] });
    assert.ok(text.endsWith('(028) 38352020 (nhánh 141, 142) · a@hcmue.edu.vn'));
  });
});

describe('findHighlight', () => {
  it('locates the query ignoring diacritics', () => {
    const text = 'Cấp giấy xác nhận học phí';
    const range = findHighlight(text, 'hoc phi');
    assert.ok(range);
    assert.equal(text.slice(range[0], range[1]), 'học phí');
  });
  it('returns null when absent', () => {
    assert.equal(findHighlight('abc', 'xyz'), null);
  });
});

describe('directory data', () => {
  it('gives every office at least one email', () => {
    for (const office of OFFICES) assert.ok(office.emails.length > 0, office.name);
  });
  it('has a faculty without a phone and no invented number for it', () => {
    const withoutPhone = FACULTIES.filter((unit) => unit.phones.length === 0);
    assert.ok(withoutPhone.length > 0);
  });
  it('keeps the two Tổ Đào tạo – Khảo thí – Công tác sinh viên entries on different campuses', () => {
    const groups = FACULTIES.filter((unit) => unit.name.startsWith('Tổ Đào tạo – Khảo thí – Công tác sinh viên'));
    assert.equal(groups.length, 2);
    assert.notEqual(groups[0].campus, groups[1].campus);
  });
});
