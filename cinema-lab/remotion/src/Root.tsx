import React from 'react';
import { Composition } from 'remotion';
import { TextReveal, TextRevealProps } from './templates/TextReveal';
import { ImageSlideshow, ImageSlideshowProps } from './templates/ImageSlideshow';
import { NarrationReel, NarrationReelProps } from './templates/NarrationReel';
import { TitleCard, TitleCardProps } from './templates/TitleCard';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="TextReveal"
        component={TextReveal}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ text: 'Make it magical', accent_color: '#e86800', duration_frames: 450 }}
        calculateMetadata={async ({ props }: { props: TextRevealProps }) => ({
          durationInFrames: props.duration_frames,
        })}
      />
      <Composition
        id="ImageSlideshow"
        component={ImageSlideshow}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ images: [], captions: [], duration_frames: 450 }}
        calculateMetadata={async ({ props }: { props: ImageSlideshowProps }) => ({
          durationInFrames: props.duration_frames,
        })}
      />
      <Composition
        id="NarrationReel"
        component={NarrationReel}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ audio: '', clips: [], captions: [], duration_frames: 450 }}
        calculateMetadata={async ({ props }: { props: NarrationReelProps }) => ({
          durationInFrames: props.duration_frames,
        })}
      />
      <Composition
        id="TitleCard"
        component={TitleCard}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ title: 'OPENCLAW', bg_color: '#060606', duration_frames: 450 }}
        calculateMetadata={async ({ props }: { props: TitleCardProps }) => ({
          durationInFrames: props.duration_frames,
        })}
      />
    </>
  );
};
