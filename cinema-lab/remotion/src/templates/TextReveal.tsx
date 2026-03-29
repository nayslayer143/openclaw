import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, staticFile, Img } from 'remotion';

export type TextRevealProps = {
  text: string;
  accent_color: string;
  bg_asset?: string;
  duration_frames: number;
};

export const TextReveal: React.FC<TextRevealProps> = ({
  text,
  accent_color,
  bg_asset,
  duration_frames,
}) => {
  const frame = useCurrentFrame();
  const words = text.split(' ');
  const framesPerWord = Math.max(8, duration_frames / words.length);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#060606',
        justifyContent: 'center',
        alignItems: 'center',
        padding: 60,
      }}
    >
      {bg_asset && (
        <AbsoluteFill>
          <Img
            src={staticFile(bg_asset)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              filter: 'blur(20px)',
              opacity: 0.3,
            }}
          />
        </AbsoluteFill>
      )}
      <div
        style={{
          textAlign: 'center',
          fontFamily: 'monospace',
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: 16,
        }}
      >
        {words.map((word, i) => {
          const startFrame = i * framesPerWord;
          const opacity = interpolate(
            frame,
            [startFrame, startFrame + 8],
            [0, 1],
            { extrapolateRight: 'clamp', extrapolateLeft: 'clamp' }
          );
          const y = interpolate(
            frame,
            [startFrame, startFrame + 8],
            [30, 0],
            { extrapolateRight: 'clamp', extrapolateLeft: 'clamp' }
          );
          return (
            <span
              key={i}
              style={{
                color: i % 3 === 0 ? accent_color : '#f0ece4',
                fontSize: 80,
                fontWeight: 700,
                opacity,
                transform: `translateY(${y}px)`,
                letterSpacing: 2,
                display: 'inline-block',
              }}
            >
              {word}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
