import { describe, expect, it } from 'vitest';
import { esc, ctx, shortModelName, renderNotesParts, parseNotesFlags } from '../../web/app.js';

describe('UI Helper Functions (web/app.js)', () => {
  describe('esc()', () => {
    it('escapes HTML special characters correctly', () => {
      expect(esc('<script>alert("xss")</script>')).toBe('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;');
      expect(esc('A & B')).toBe('A &amp; B');
    });
  });

  describe('ctx()', () => {
    it('formats context length numbers cleanly', () => {
      expect(ctx(null)).toBe('-');
      expect(ctx(262144)).toBe('262K');
      expect(ctx(1000000)).toBe('1M');
      expect(ctx(500)).toBe('500');
    });
  });

  describe('shortModelName()', () => {
    it('truncates model names longer than 32 characters', () => {
      expect(shortModelName('Qwen/Qwen2.5-Coder-32B-Instruct')).toBe('Qwen/Qwen2.5-Coder-32B-Instruct');
      expect(shortModelName('DeepSeek-R1-Distill-Qwen-32B-GGUF-Q4_K_M')).toBe('DeepSeek-R1-Distill-Qwen-32B-GGU…');
    });
  });

  describe('parseNotesFlags()', () => {
    it('extracts boolean flags from notes string or object', () => {
      expect(parseNotesFlags('loaded into vram')).toEqual({ loaded_into_vram: true, insufficient: false });
      expect(parseNotesFlags('insufficient vram')).toEqual({ loaded_into_vram: false, insufficient: true });
    });
  });

  describe('renderNotesParts()', () => {
    it('parses notes string/array into cleanly separated list items', () => {
      expect(renderNotesParts('fast; accurate; recommended')).toEqual(['fast', 'accurate', 'recommended']);
    });
  });
});
