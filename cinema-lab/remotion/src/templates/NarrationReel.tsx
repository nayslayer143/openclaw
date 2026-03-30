import React from 'react';
import { AbsoluteFill, Audio, interpolate, useCurrentFrame, Sequence, Img, staticFile } from 'remotion';

export type NarrationReelProps = {
  audio: string;
  clips: string[];
  captions: string[];
  duration_frames: number;
};

const ClipFrame: React.FC<{ src: string; caption: string; totalFrames: number }> = ({
  src,
  caption,
  totalFrames,
}) => {
  const frame = useCurrentFrame();
  const fadeIn = Math.min(8, Math.floor(totalFrames / 3));
  const fadeOutStart = Math.max(fadeIn, totalFrames - Math.floor(totalFrames / 3));
  const opacity = interpolate(
    frame,
    [0, fadeIn, fadeOutStart, totalFrames],
    [0, 1, 1, 0],
    { extrapolateRight: 'clamp', extrapolateLeft: 'clamp' }
  );
  const captionOpacity = interpolate(frame, [10, 22], [0, 1], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill style={{ opacity }}>
      <Img src={staticFile(src)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          padding: '80px 40px 60px',
          background: 'linear-gradient(transparent, rgba(0,0,0,0.88))',
        }}
      >
        <div
          style={{
            color: '#f0ece4',
            fontSize: 38,
            fontFamily: 'monospace',
            opacity: captionOpacity,
            letterSpacing: 0.5,
            lineHeight: 1.5,
          }}
        >
          {caption}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const NarrationReel: React.FC<NarrationReelProps> = ({
  audio,
  clips: clipsRaw,
  captions: captionsRaw,
  duration_frames,
}) => {
  const clips = Array.isArray(clipsRaw) ? clipsRaw : [];
  const captions = Array.isArray(captionsRaw) ? captionsRaw : [];
  const framesPerClip = clips.length > 0 ? Math.floor(duration_frames / clips.length) : duration_frames;

  return (
    <AbsoluteFill style={{ backgroundColor: '#060606' }}>
      {audio && <Audio src={staticFile(audio)} />}
      {clips.map((clip, i) => {
        const isLast = i === clips.length - 1;
        const clipDuration = isLast ? duration_frames - i * framesPerClip : framesPerClip;
        return (
          <Sequence key={`${i}-${clip}`} from={i * framesPerClip} durationInFrames={clipDuration}>
            <ClipFrame src={clip} caption={captions[i] ?? ''} totalFrames={clipDuration} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
