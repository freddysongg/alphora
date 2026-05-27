"use client";

import { forwardRef } from "react";
import type {
  ComponentPropsWithoutRef,
  ElementRef,
  ForwardedRef,
  ReactElement,
} from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";
import { cn } from "@/lib/cn";

type SliderRootProps = ComponentPropsWithoutRef<typeof SliderPrimitive.Root>;

const rootClasses =
  "relative flex w-full touch-none select-none items-center h-5 cursor-pointer";

const trackClasses =
  "relative h-1 w-full grow overflow-hidden rounded-full bg-[#1a1426]";

const rangeClasses =
  "absolute h-full rounded-full bg-[linear-gradient(90deg,#7a4dff_0%,#9970ff_100%)] shadow-[0_0_10px_-2px_rgba(122,77,255,0.55)]";

const thumbClasses =
  "block h-[14px] w-[14px] rounded-full bg-[#d8b4fe] border-2 border-canvas shadow-[0_0_0_3px_rgba(122,77,255,0.18)] transition-shadow duration-150 ease-[var(--ease-out)] hover:shadow-[0_0_0_5px_rgba(122,77,255,0.22)] focus-visible:shadow-[0_0_0_5px_rgba(122,77,255,0.4)] focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50";

function SliderImpl(
  props: SliderRootProps,
  ref: ForwardedRef<ElementRef<typeof SliderPrimitive.Root>>,
): ReactElement {
  const { className, defaultValue, value, ...rest } = props;
  const resolvedSeed = value ?? defaultValue ?? ([0] as readonly number[]);
  return (
    <SliderPrimitive.Root
      ref={ref}
      className={cn(rootClasses, className)}
      defaultValue={defaultValue}
      value={value}
      {...rest}
    >
      <SliderPrimitive.Track className={trackClasses}>
        <SliderPrimitive.Range className={rangeClasses} />
      </SliderPrimitive.Track>
      {resolvedSeed.map((_unused, index) => (
        <SliderPrimitive.Thumb
          key={index}
          className={thumbClasses}
          aria-label={props["aria-label"]}
        />
      ))}
    </SliderPrimitive.Root>
  );
}

export const Slider = forwardRef<
  ElementRef<typeof SliderPrimitive.Root>,
  SliderRootProps
>(SliderImpl);
Slider.displayName = "Slider";
