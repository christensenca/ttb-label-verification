import { describe, expect, it } from 'vitest'
import { rowColorClass } from '../FieldRow'
import type { components } from '../../api/generated'

type Field = components['schemas']['FieldRowOut']

function makeField(overrides: Partial<Field>): Field {
  return {
    id: 'cmp-1',
    field: 'brand',
    extracted_value: 'X',
    expected_value: 'X',
    model_verdict: 'pass',
    effective_verdict: 'pass',
    rule: 'exact',
    reason: null,
    confidence: 'hi',
    diff_extracted: null,
    diff_expected: null,
    override: null,
    ...overrides,
  }
}

describe('rowColorClass — tri-state per R11', () => {
  it('returns green for (pass, hi, text)', () => {
    const f = makeField({ field: 'brand', effective_verdict: 'pass', confidence: 'hi' })
    expect(rowColorClass(f)).toBe('green')
  })

  it('returns yellow for (pass, low, text)', () => {
    const f = makeField({ field: 'brand', effective_verdict: 'pass', confidence: 'low' })
    expect(rowColorClass(f)).toBe('yellow')
  })

  it('returns yellow for (pass, med, text)', () => {
    const f = makeField({ field: 'brand', effective_verdict: 'pass', confidence: 'med' })
    expect(rowColorClass(f)).toBe('yellow')
  })

  it('returns green for (pass, null, non-text: is_imported)', () => {
    const f = makeField({
      field: 'is_imported',
      effective_verdict: 'pass',
      confidence: null,
    })
    expect(rowColorClass(f)).toBe('green')
  })

  it('returns green for (pass, null, non-text: government_warning_style)', () => {
    const f = makeField({
      field: 'government_warning_style',
      effective_verdict: 'pass',
      confidence: null,
    })
    expect(rowColorClass(f)).toBe('green')
  })

  it('returns red for fail regardless of confidence/field', () => {
    expect(
      rowColorClass(makeField({ effective_verdict: 'fail', confidence: 'hi' })),
    ).toBe('red')
    expect(
      rowColorClass(
        makeField({
          field: 'government_warning_style',
          effective_verdict: 'fail',
          confidence: null,
        }),
      ),
    ).toBe('red')
    expect(
      rowColorClass(makeField({ effective_verdict: 'fail', confidence: 'low' })),
    ).toBe('red')
  })

  it('returns grey for not_applicable regardless of confidence/field', () => {
    expect(
      rowColorClass(
        makeField({ effective_verdict: 'not_applicable', confidence: 'hi' }),
      ),
    ).toBe('grey')
    expect(
      rowColorClass(
        makeField({
          field: 'country_of_origin',
          effective_verdict: 'not_applicable',
          confidence: null,
        }),
      ),
    ).toBe('grey')
  })

  it('never returns yellow for non-text fields (no confidence available)', () => {
    // government_warning_style passes with no confidence — must be green, not yellow.
    expect(
      rowColorClass(
        makeField({
          field: 'government_warning_style',
          effective_verdict: 'pass',
          confidence: null,
        }),
      ),
    ).toBe('green')
    // is_imported passes with no confidence — must be green, not yellow.
    expect(
      rowColorClass(
        makeField({
          field: 'is_imported',
          effective_verdict: 'pass',
          confidence: null,
        }),
      ),
    ).toBe('green')
  })
})
