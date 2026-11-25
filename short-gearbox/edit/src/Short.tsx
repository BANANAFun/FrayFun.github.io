// Шортс: видео из Blender + голос + музыка + эмбиент + звуки по событиям + субтитры 2–3 слова.
import React from "react";
import { AbsoluteFill, Audio, OffthreadVideo, Sequence, continueRender, delayRender, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import plan from "./plan.json";

// шрифт лежит локально в public/ (Google Fonts через прокси недоступен браузеру рендера)
const fontFamily = "MontserratBlack";
const fontHandle = delayRender("font");
new FontFace(fontFamily, `url(${staticFile("Montserrat-900.ttf")})`, { weight: "900" }).load().then((f) => {
  document.fonts.add(f);
  continueRender(fontHandle);
});

const Caption: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const g = plan.groups.find((x) => f >= x.start && f < Math.max(x.end, x.start + 6));
  if (!g) return null;
  const s = spring({ frame: f - g.start, fps, config: { damping: 11, stiffness: 240, mass: 0.55 } });
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 620 }}>
      <div style={{ fontFamily, fontWeight: 900, fontSize: 88, lineHeight: 1.05, color: "white", textAlign: "center", maxWidth: 940,
        transform: `scale(${interpolate(s, [0, 1], [0.72, 1])})`, WebkitTextStroke: "14px black", paintOrder: "stroke fill",
        textShadow: "0 6px 0 rgba(0,0,0,0.55)" }}>
        {g.text}
      </div>
    </AbsoluteFill>
  );
};

const fade = (f: number, total: number, level: number) =>
  interpolate(f, [0, 20, total - 45, total], [0, level, level, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

export const Short: React.FC = () => {
  const { durationInFrames } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      <OffthreadVideo src={staticFile("video.mp4")} muted style={{ width: "100%", height: "100%" }} />
      <Audio src={staticFile("voice.mp3")} />
      <Audio src={staticFile("music.wav")} volume={(f) => fade(f, durationInFrames, plan.musicVolume)} />
      {plan.rain.map((r, i) => (
        <Sequence key={"rain" + i} from={r.from} durationInFrames={r.dur}>
          <Audio src={staticFile("amb_rain.wav")} loop volume={(f) => interpolate(f, [0, 8, r.dur - 10, r.dur], [0, plan.ambienceVolume, plan.ambienceVolume, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })} />
        </Sequence>
      ))}
      {plan.sfx.map((s, i) => (
        <Sequence key={i} from={Math.max(0, s.f)}>
          <Audio src={staticFile(`${s.k}.wav`)} volume={s.v} />
        </Sequence>
      ))}
      <Caption />
    </AbsoluteFill>
  );
};
