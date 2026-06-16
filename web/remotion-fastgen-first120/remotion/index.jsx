import React from "react";
import {
  AbsoluteFill,
  Audio,
  Composition,
  Easing,
  Img,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import {DURATION_IN_FRAMES, FPS, HEIGHT, WIDTH, scenePlan} from "./fastgenFirst120Data";

const SAFE_X = 108;
const SAFE_Y = 88;

const COLORS = {
  bg: "#040507",
  text: "#f3f1eb",
  soft: "rgba(243,241,235,0.76)",
  line: "rgba(243,241,235,0.48)",
  muted: "rgba(243,241,235,0.18)",
  accent: "#c55a38",
  teal: "#5d8a90",
  warm: "#d8b47a",
  panel: "rgba(6,8,11,0.58)",
};

const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));
const mix = (from, to, progress) => from + (to - from) * progress;
const ease = (value) => Easing.bezier(0.22, 1, 0.36, 1)(clamp(value));
const reveal = (frame, delay = 0, length = 18) => clamp((frame - delay) / length);
const fadeWindow = (frame, duration, inFrames = 12, outFrames = 16) =>
  Math.min(clamp(frame / Math.max(inFrames, 1)), clamp((duration - frame) / Math.max(outFrames, 1)));

const stage = {
  fontFamily: "Inter, Arial, Helvetica, sans-serif",
  textTransform: "uppercase",
  letterSpacing: "0.07em",
};

const SceneShell = ({children}) => (
  <div
    style={{
      position: "absolute",
      inset: `${SAFE_Y}px ${SAFE_X}px`,
      pointerEvents: "none",
    }}
  >
    {children}
  </div>
);

const GrainOverlay = () => (
  <div
    style={{
      position: "absolute",
      inset: 0,
      opacity: 0.05,
      mixBlendMode: "screen",
      backgroundImage:
        "radial-gradient(circle at 20% 24%, rgba(255,255,255,0.75) 0 0.8px, transparent 1px), radial-gradient(circle at 70% 32%, rgba(255,255,255,0.55) 0 0.7px, transparent 1px), radial-gradient(circle at 48% 76%, rgba(255,255,255,0.7) 0 0.8px, transparent 1px)",
      backgroundSize: "20px 20px, 24px 24px, 28px 28px",
    }}
  />
);

const Vignette = ({warm = false}) => (
  <div
    style={{
      position: "absolute",
      inset: 0,
      background: warm
        ? "radial-gradient(circle at 50% 20%, rgba(216,180,122,0.08), transparent 25%), linear-gradient(180deg, rgba(13,11,7,0.08), rgba(8,6,4,0.44) 88%)"
        : "radial-gradient(circle at 32% 18%, rgba(255,255,255,0.08), transparent 24%), linear-gradient(180deg, rgba(5,8,11,0.12), rgba(2,3,5,0.6) 92%)",
    }}
  />
);

const Chip = ({label, x, y, width = 260, opacity = 1, accent = false, warm = false}) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      width,
      padding: "12px 18px",
      border: `1px solid ${accent ? "rgba(197,90,56,0.84)" : warm ? "rgba(216,180,122,0.66)" : COLORS.line}`,
      background: accent ? "rgba(197,90,56,0.14)" : warm ? "rgba(56,40,18,0.3)" : COLORS.panel,
      color: COLORS.text,
      ...stage,
      fontSize: 24,
      opacity,
      backdropFilter: "blur(10px)",
      boxShadow: accent ? "0 0 28px rgba(197,90,56,0.15)" : "0 18px 44px rgba(0,0,0,0.22)",
    }}
  >
    {label}
  </div>
);

const CaptionBlock = ({kicker, headline, subline, frame, align = "left", warm = false}) => {
  const intro = ease(reveal(frame, 0, 22));
  const shift = mix(18, 0, intro);
  return (
    <div
      style={{
        position: "absolute",
        [align]: 0,
        top: warm ? 92 : 76,
        maxWidth: 900,
        opacity: intro,
        transform: `translateY(${shift}px)`,
      }}
    >
      <div
        style={{
          ...stage,
          fontSize: 24,
          color: warm ? COLORS.warm : COLORS.teal,
          marginBottom: 20,
        }}
      >
        {kicker}
      </div>
      <div
        style={{
          ...stage,
          whiteSpace: "pre-line",
          fontSize: headline.length > 46 ? 62 : 76,
          fontWeight: 700,
          lineHeight: 1.02,
          color: warm ? "#f4e3be" : COLORS.text,
          textShadow: "0 18px 44px rgba(0,0,0,0.34)",
        }}
      >
        {headline}
      </div>
      <div
        style={{
          marginTop: 24,
          maxWidth: 760,
          fontFamily: "Inter, Arial, Helvetica, sans-serif",
          fontSize: 28,
          lineHeight: 1.35,
          color: warm ? "rgba(244,227,190,0.86)" : COLORS.soft,
        }}
      >
        {subline}
      </div>
    </div>
  );
};

const ScannerSweep = ({frame, tint = "rgba(143,224,232,0.42)"}) => {
  const x = mix(-260, WIDTH - SAFE_X * 2 + 260, ease(frame / 120));
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: 0,
        width: 180,
        bottom: 0,
        background: `linear-gradient(90deg, transparent 0%, ${tint} 50%, transparent 100%)`,
        mixBlendMode: "screen",
        opacity: 0.7,
      }}
    />
  );
};

const SceneBackdrop = ({scene, frame, duration, warm = false, tertiary = false}) => {
  const progress = ease(frame / Math.max(duration - 1, 1));
  const primaryZoom = mix(1.05, scene.id === "S01" ? 1.12 : warm ? 1.08 : 1.03, progress);
  const primaryX = scene.id === "S07" ? mix(-44, 32, progress) : mix(-18, 24, progress);
  const primaryY = warm ? mix(18, -8, progress) : mix(8, -12, progress);
  const detailOpacity = scene.assets.detail ? clamp((frame - duration * 0.38) / (duration * 0.22)) * clamp((duration - frame) / (duration * 0.18)) : 0;
  const deepOpacity = scene.assets.deep ? clamp((frame - duration * 0.55) / (duration * 0.18)) : 0;

  return (
    <AbsoluteFill style={{backgroundColor: COLORS.bg, overflow: "hidden"}}>
      <Img
        src={staticFile(scene.assets.bg)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `translate(${primaryX}px, ${primaryY}px) scale(${primaryZoom})`,
          filter: warm ? "brightness(0.78) saturate(0.88) contrast(1.06)" : "brightness(0.68) saturate(0.82) contrast(1.08)",
        }}
      />
      {scene.assets.detail ? (
        <Img
          src={staticFile(scene.assets.detail)}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            opacity: detailOpacity,
            transform: `scale(${mix(1.02, 1.08, progress)})`,
            filter: warm ? "brightness(0.88) saturate(0.9)" : "brightness(0.74) saturate(0.9)",
          }}
        />
      ) : null}
      {tertiary && scene.assets.brands ? (
        <Img
          src={staticFile(scene.assets.brands)}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            opacity: clamp((frame - duration * 0.18) / (duration * 0.16)) * 0.7,
            transform: `translate(${mix(40, -12, progress)}px, 0px) scale(${mix(1.02, 1.1, progress)})`,
            filter: "brightness(0.72) saturate(0.8)",
          }}
        />
      ) : null}
      {scene.assets.deep ? (
        <Img
          src={staticFile(scene.assets.deep)}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            opacity: deepOpacity * 0.66,
            transform: `scale(${mix(1, 1.04, progress)})`,
            filter: "brightness(0.56) saturate(0.8)",
          }}
        />
      ) : null}
      <Vignette warm={warm} />
      <GrainOverlay />
    </AbsoluteFill>
  );
};

const SceneS01 = ({scene, frame}) => (
  <SceneShell>
    <CaptionBlock kicker={scene.kicker} headline={scene.headline} subline={scene.subline} frame={frame} />
    <ScannerSweep frame={frame} />
    {scene.chips.map((chip, index) => {
      const local = reveal(frame, 16 + index * 8, 14);
      const x = 30 + index * 300;
      return (
        <React.Fragment key={chip}>
          <div
            style={{
              position: "absolute",
              left: x,
              top: 260 + (index % 2) * 36,
              width: 238,
              height: 300,
              border: `1px solid rgba(243,241,235,${mix(0.06, 0.45, local)})`,
              opacity: local,
            }}
          />
          <Chip label={chip} x={x} y={590 + (index % 2) * 30} width={238} opacity={local} />
        </React.Fragment>
      );
    })}
  </SceneShell>
);

const SceneS02 = ({scene, frame, duration}) => {
  const mazeOpacity = clamp((frame - 26) / 30);
  return (
    <SceneShell>
      <CaptionBlock kicker={scene.kicker} headline={scene.headline} subline={scene.subline} frame={frame} align="right" />
      <div
        style={{
          position: "absolute",
          left: 120,
          top: 160,
          width: 640,
          height: 510,
          border: "1px solid rgba(243,241,235,0.18)",
          opacity: mazeOpacity,
        }}
      />
      {[0, 1, 2].map((step) => (
        <div
          key={step}
          style={{
            position: "absolute",
            left: 120 + step * 180,
            top: 220 + (step % 2) * 70,
            width: 160,
            height: 220,
            border: "1px solid rgba(243,241,235,0.26)",
            opacity: clamp((frame - 18 - step * 12) / 16) * 0.8,
          }}
        />
      ))}
      <div
        style={{
          position: "absolute",
          left: 310,
          top: 620,
          width: 1,
          height: 110,
          background: COLORS.line,
          opacity: fadeWindow(frame, duration, 20, 18),
        }}
      />
    </SceneShell>
  );
};

const SceneS03 = ({scene, frame}) => (
  <SceneShell>
    <CaptionBlock kicker={scene.kicker} headline={scene.headline} subline={scene.subline} frame={frame} />
    <div style={{position: "absolute", left: 0, right: 0, top: 470, height: 2, background: COLORS.muted}} />
    {scene.chips.map((chip, index) => {
      const local = reveal(frame, 22 + index * 12, 16);
      return <Chip key={chip} label={chip} x={70 + index * 360} y={index % 2 === 0 ? 520 : 650} width={270} opacity={local} />;
    })}
    <Chip label="ПОЛКА" x={0} y={780} width={220} opacity={reveal(frame, 72, 18)} accent />
  </SceneShell>
);

const SceneS04 = ({scene, frame}) => (
  <SceneShell>
    <CaptionBlock kicker={scene.kicker} headline={scene.headline} subline={scene.subline} frame={frame} align="right" />
    {new Array(9).fill(null).map((_, index) => {
      const local = reveal(frame, 12 + index * 4, 12);
      return (
        <div
          key={index}
          style={{
            position: "absolute",
            left: 40 + (index % 3) * 280,
            top: 200 + Math.floor(index / 3) * 150,
            width: 220,
            height: 100,
            border: `1px solid rgba(243,241,235,${mix(0.06, 0.22, local)})`,
            background: "rgba(243,241,235,0.025)",
            opacity: local,
          }}
        />
      );
    })}
    <div style={{position: "absolute", left: 150, top: 280, width: 520, height: 1, background: COLORS.line, transform: "rotate(18deg)", opacity: 0.22}} />
    <div style={{position: "absolute", left: 180, top: 420, width: 420, height: 1, background: COLORS.line, transform: "rotate(-14deg)", opacity: 0.22}} />
  </SceneShell>
);

const SceneS05 = ({scene, frame, duration}) => {
  const gateX = 760;
  return (
    <SceneShell>
      <CaptionBlock kicker={scene.kicker} headline={scene.headline} subline={scene.subline} frame={frame} />
      <div
        style={{
          position: "absolute",
          left: gateX,
          top: 160,
          width: 110,
          height: 520,
          border: `1px solid ${COLORS.line}`,
          background: "rgba(255,255,255,0.03)",
        }}
      />
      {scene.chips.map((chip, index) => {
        const local = ease(clamp((frame - 18 - index * 7) / Math.max(duration - 100, 1)));
        const x = mix(20, 1130, local);
        return <Chip key={chip} label={chip} x={x} y={250 + index * 62} width={250} opacity={clamp(local * 1.18)} accent={index === 0 || index === 4} />;
      })}
      <Chip label="ОЩУЩЕНИЕ СВОБОДЫ" x={1060} y={650} width={430} opacity={reveal(frame, 118, 18)} accent />
    </SceneShell>
  );
};

const SceneS06 = ({scene, frame}) => (
  <SceneShell>
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: "radial-gradient(circle at 50% 26%, rgba(255,225,173,0.22), transparent 18%), linear-gradient(90deg, rgba(0,0,0,0.6) 0%, transparent 22%, transparent 78%, rgba(0,0,0,0.6) 100%)",
      }}
    />
    <CaptionBlock kicker={scene.kicker} headline={scene.headline} subline={scene.subline} frame={frame} warm />
    <Chip label="ПОЛКИ = СЦЕНА" x={760} y={260} width={430} opacity={reveal(frame, 26, 18)} warm />
    <Chip label="БРЕНДЫ = АКТЁРЫ" x={920} y={380} width={470} opacity={reveal(frame, 48, 18)} warm />
  </SceneShell>
);

const SceneS07 = ({scene, frame}) => (
  <SceneShell>
    <CaptionBlock kicker={scene.kicker} headline={scene.headline} subline={scene.subline} frame={frame} />
    <div style={{position: "absolute", left: 920, top: 170, width: 1, height: 520, background: COLORS.muted}} />
    {scene.chips.map((chip, index) => (
      <Chip key={chip} label={chip} x={index % 2 === 0 ? 1010 : 1110} y={220 + index * 104} width={340} opacity={reveal(frame, 28 + index * 10, 16)} />
    ))}
    <Chip label="ЗА КАДРОМ" x={0} y={640} width={290} opacity={reveal(frame, 96, 18)} accent />
  </SceneShell>
);

const SceneS08 = ({scene, frame}) => (
  <SceneShell>
    <CaptionBlock kicker={scene.kicker} headline={scene.headline} subline={scene.subline} frame={frame} warm />
    {scene.chips.map((chip, index) => (
      <div
        key={chip}
        style={{
          position: "absolute",
          left: 20 + index * 220,
          top: 610 - (index % 2) * 70,
          ...stage,
          fontSize: index === 0 ? 58 : 44,
          color: index < 3 ? "#f4e3be" : COLORS.warm,
          opacity: reveal(frame, 18 + index * 8, 14),
          borderBottom: "1px solid rgba(216,180,122,0.34)",
          paddingBottom: 10,
        }}
      >
        {chip}
      </div>
    ))}
  </SceneShell>
);

const SceneS09 = ({scene, frame}) => (
  <SceneShell>
    <CaptionBlock kicker={scene.kicker} headline={scene.headline} subline={scene.subline} frame={frame} warm />
    {scene.chips.map((chip, index) => (
      <Chip key={chip} label={chip} x={50 + index * 320} y={520 + (index % 2) * 46} width={250} opacity={reveal(frame, 24 + index * 10, 14)} warm />
    ))}
  </SceneShell>
);

const SceneS10 = ({scene, frame}) => {
  const lineProgress = ease(reveal(frame, 24, 46));
  return (
    <SceneShell>
      <CaptionBlock kicker={scene.kicker} headline={scene.headline} subline={scene.subline} frame={frame} warm />
      <div style={{position: "absolute", left: 140, top: 560, width: 540, height: 2, background: "rgba(216,180,122,0.18)"}} />
      <div style={{position: "absolute", left: 140, top: 560, width: 540 * lineProgress, height: 2, background: COLORS.warm, boxShadow: "0 0 18px rgba(216,180,122,0.35)"}} />
      <Chip label="ПОЛЕ" x={140} y={500} width={180} opacity={reveal(frame, 10, 14)} warm />
      <Chip label="МЕЛЬНИЦА" x={360} y={500} width={220} opacity={reveal(frame, 26, 14)} warm />
      <Chip label="ХЛЕБ" x={620} y={500} width={180} opacity={reveal(frame, 42, 14)} accent />
    </SceneShell>
  );
};

const renderSceneOverlay = (scene, frame, duration) => {
  switch (scene.id) {
    case "S01":
      return <SceneS01 scene={scene} frame={frame} duration={duration} />;
    case "S02":
      return <SceneS02 scene={scene} frame={frame} duration={duration} />;
    case "S03":
      return <SceneS03 scene={scene} frame={frame} duration={duration} />;
    case "S04":
      return <SceneS04 scene={scene} frame={frame} duration={duration} />;
    case "S05":
      return <SceneS05 scene={scene} frame={frame} duration={duration} />;
    case "S06":
      return <SceneS06 scene={scene} frame={frame} duration={duration} />;
    case "S07":
      return <SceneS07 scene={scene} frame={frame} duration={duration} />;
    case "S08":
      return <SceneS08 scene={scene} frame={frame} duration={duration} />;
    case "S09":
      return <SceneS09 scene={scene} frame={frame} duration={duration} />;
    case "S10":
      return <SceneS10 scene={scene} frame={frame} duration={duration} />;
    default:
      return null;
  }
};

const SceneRenderer = ({scene}) => {
  const frame = useCurrentFrame();
  const localFrame = frame;
  const opacity = fadeWindow(localFrame, scene.duration, 10, 12);
  const warm = scene.id === "S06" || scene.id === "S08" || scene.id === "S09" || scene.id === "S10";
  return (
    <AbsoluteFill style={{opacity}}>
      <SceneBackdrop scene={scene} frame={localFrame} duration={scene.duration} warm={warm} tertiary={scene.id === "S05"} />
      {renderSceneOverlay(scene, localFrame, scene.duration)}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `linear-gradient(180deg, rgba(0,0,0,${interpolate(localFrame, [0, scene.duration], [0.08, 0.2])}), transparent 26%, rgba(0,0,0,0.32) 100%)`,
        }}
      />
    </AbsoluteFill>
  );
};

const FastGenFirst120 = () => (
  <AbsoluteFill style={{backgroundColor: COLORS.bg}}>
    <Audio src={staticFile("fastgen_first120/audio/source_audio.mp3")} />
    {scenePlan.map((scene) => (
      <Sequence key={scene.id} from={scene.start} durationInFrames={scene.duration}>
        <SceneRenderer scene={scene} />
      </Sequence>
    ))}
  </AbsoluteFill>
);

export const RemotionRoot = () => (
  <Composition
    id="FastGenFirst120"
    component={FastGenFirst120}
    durationInFrames={DURATION_IN_FRAMES}
    fps={FPS}
    width={WIDTH}
    height={HEIGHT}
  />
);

export default RemotionRoot;
