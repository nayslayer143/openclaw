import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, Sequence, Img, staticFile } from 'remotion';

export type ImageSlideshowProps = {
  images: string[];
  captions?: string[];
  duration_frames: number;
};

const SlideFrame: React.FC<{ src: string; caption?: string; totalFrames: number }> = ({
  src,
  caption,
  totalFrames,
}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, totalFrames], [1, 1.08]);
  const fadeOutStart = Math.max(10, totalFrames - 10);
  const opacity = interpolate(
    frame,
    [0, 10, fadeOutStart, totalFrames],
    [0, 1, 1, 0],
    { extrapolateRight: 'clamp', extrapolateLeft: 'clamp' }
  );

  return (
    <AbsoluteFill style={{ opacity }}>
      <Img
        src={staticFile(src)}
        style={{ width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${scale})` }}
      />
      {caption && (
        <div
          style={{
            position: 'absolute',
            bottom: 80,
            left: 40,
            right: 40,
            color: '#f0ece4',
            fontSize: 40,
            fontFamily: 'monospace',
            textShadow: '0 2px 12px rgba(0,0,0,0.9)',
            letterSpacing: 1,
            lineHeight: 1.4,
          }}
        >
          {caption}
        </div>
      )}
    </AbsoluteFill>
  );
};

export const ImageSlideshow: React.FC<ImageSlideshowProps> = ({
  images,
  captions,
  duration_frames,
}) => {
  if (images.length === 0) return <AbsoluteFill style={{ backgroundColor: '#060606' }} />;
  const framesPerImage = Math.floor(duration_frames / images.length);

  return (
    <AbsoluteFill style={{ backgroundColor: '#060606' }}>
      {images.map((img, i) => {
        const isLast = i === images.length - 1;
        const slideDuration = isLast ? duration_frames - i * framesPerImage : framesPerImage;
        return (
          <Sequence key={img} from={i * framesPerImage} durationInFrames={slideDuration}>
            <SlideFrame src={img} caption={captions?.[i]} totalFrames={slideDuration} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
