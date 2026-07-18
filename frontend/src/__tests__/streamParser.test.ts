import { describe, expect, it } from "vitest";
import { createFrameParser } from "../api/streamParser";

const EV = (json: string) => `event: stage\ndata: ${json}\n\n`;

describe("createFrameParser", () => {
  it("parses a complete event", () => {
    const parse = createFrameParser();
    expect(parse(EV('{"stage":"retrieve"}'))).toEqual([{ stage: "retrieve" }]);
  });

  it("buffers partial chunks until the event terminator arrives", () => {
    const parse = createFrameParser();
    expect(parse('event: stage\ndata: {"stage":"exe')).toEqual([]);
    expect(parse('cute"}\n\n')).toEqual([{ stage: "execute" }]);
  });

  it("returns multiple frames from one chunk, in order", () => {
    const parse = createFrameParser();
    const frames = parse(
      EV('{"stage":"validate","ok":false,"reason":"Tylko SELECT."}') +
        EV('{"stage":"generate_sql","attempt":2}'),
    );
    expect(frames.map((f) => f.stage)).toEqual(["validate", "generate_sql"]);
    expect(frames[0].reason).toBe("Tylko SELECT.");
  });

  it("ignores keep-alive/comment lines without data", () => {
    const parse = createFrameParser();
    expect(parse(": ping\n\n")).toEqual([]);
  });
});
