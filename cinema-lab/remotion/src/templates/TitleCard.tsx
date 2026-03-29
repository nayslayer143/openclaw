import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, spring } from 'remotion';

export type TitleCardProps = {
  title: string;
  subtitle?: string;
  cta?: string;
  bg_color: string;
  duration_frames: number;
};

export const TitleCard: React.FC<TitleCardProps> = ({
  title,
  subtitle,
  cta,
  bg_color,
  duration_frames,
}) => {
  const frame = useCurrentFrame();
  const fps = 30;

  const titleOpacity = spring({ fps, frame, config: { damping: 80 } });
  const titleY = interpolate(frame, [0, 20], [60, 0], { extrapolateRight: 'clamp' });
  const subtitleOpacity = interpolate(frame, [15, 30], [0, 1], { extrapolateRight: 'clamp' });
  const ctaOpacity = interpolate(frame, [30, 45], [0, 1], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg_color,
        justifyContent: 'center',
        alignItems: 'center',
        flexDirection: 'column',
        gap: 32,
        padding: 80,
      }}
    >
      <div
        style={{
          color: '#f0ece4',
          fontSize: 96,
          fontWeight: 700,
          fontFamily: 'monospace',
          textAlign: 'center',
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
          letterSpacing: -2,
          lineHeight: 1.1,
        }}
      >
        {title}
      </div>
      {subtitle && (
        <div
          style={{
            color: '#e86800',
            fontSize: 42,
            fontFamily: 'monospace',
            textAlign: 'center',
            opacity: subtitleOpacity,
            letterSpacing: 3,
          }}
        >
          {subtitle}
        </div>
      )}
      {cta && (
        <div
          style={{
            marginTop: 40,
            padding: '20px 48px',
            border: '2px solid #e86800',
            color: '#e86800',
            fontSize: 32,
            fontFamily: 'monospace',
            letterSpacing: 4,
            opacity: ctaOpacity,
          }}
        >
          {cta}
        </div>
      )}
    </AbsoluteFill>
  );
};
