import { describe, expect, it } from 'vitest';
import { terminalCommand } from './terminal-command';

describe('trusted terminal argument formatting', () => {
  it('keeps PowerShell interpolation and quotes literal', () => {
    expect(terminalCommand(['agent', "C:\\work dir\\owner's $(x)`file"])).toBe(
      "& 'agent' 'C:\\work dir\\owner''s $(x)`file'",
    );
  });
  it('keeps POSIX quotes and substitutions literal', () => {
    expect(terminalCommand(['agent', "/work/owner's $(x)`file"])).toBe(
      "'agent' '/work/owner'\\''s $(x)`file'",
    );
  });
});
