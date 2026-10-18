export const MAX_FRAME_BYTES = 8 * 1024 * 1024;

export class FrameTooLargeError extends Error {
  readonly code = 'FRAME_TOO_LARGE';

  constructor(maxFrameBytes: number) {
    super(`frame exceeds ${maxFrameBytes} bytes`);
    this.name = 'FrameTooLargeError';
  }
}

export class JsonLineReader {
  private buffer: Buffer = Buffer.alloc(0);

  constructor(private readonly maxFrameBytes = MAX_FRAME_BYTES) {}

  feed(chunk: Buffer): string[] {
    this.buffer = this.buffer.length === 0 ? chunk : Buffer.concat([this.buffer, chunk]);

    const lines: string[] = [];
    let start = 0;
    let newline = this.buffer.indexOf(0x0a, start);

    while (newline >= 0) {
      const length = newline - start;
      if (length > this.maxFrameBytes) {
        throw new FrameTooLargeError(this.maxFrameBytes);
      }
      lines.push(this.buffer.subarray(start, newline).toString('utf8'));
      start = newline + 1;
      newline = this.buffer.indexOf(0x0a, start);
    }

    if (start > 0) this.buffer = this.buffer.subarray(start);
    if (this.buffer.length > this.maxFrameBytes) {
      throw new FrameTooLargeError(this.maxFrameBytes);
    }

    return lines;
  }
}
