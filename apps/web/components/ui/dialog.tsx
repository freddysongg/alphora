"use client";

import { forwardRef } from "react";
import type {
  ComponentPropsWithoutRef,
  ElementRef,
  ForwardedRef,
  HTMLAttributes,
  ReactElement,
} from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "@phosphor-icons/react/dist/ssr";
import { cn } from "@/lib/cn";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogPortal = DialogPrimitive.Portal;
export const DialogClose = DialogPrimitive.Close;

type DialogOverlayProps = ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>;

const overlayClasses =
  "fixed inset-0 z-50 bg-canvas/80 backdrop-blur-sm data-[state=open]:opacity-100 data-[state=closed]:opacity-0 transition-opacity duration-[200ms] ease-[var(--ease-out)]";

function DialogOverlayImpl(
  props: DialogOverlayProps,
  ref: ForwardedRef<ElementRef<typeof DialogPrimitive.Overlay>>,
): ReactElement {
  const { className, ...rest } = props;
  return (
    <DialogPrimitive.Overlay
      ref={ref}
      className={cn(overlayClasses, className)}
      {...rest}
    />
  );
}

export const DialogOverlay = forwardRef<
  ElementRef<typeof DialogPrimitive.Overlay>,
  DialogOverlayProps
>(DialogOverlayImpl);
DialogOverlay.displayName = "DialogOverlay";

interface DialogContentOwnProps {
  hideCloseButton?: boolean;
}

type DialogContentProps = ComponentPropsWithoutRef<typeof DialogPrimitive.Content> &
  DialogContentOwnProps;

const contentClasses =
  "fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 bg-surface border border-line rounded-xl shadow-[var(--shadow-popover)] p-6 data-[state=open]:opacity-100 data-[state=open]:scale-100 data-[state=closed]:opacity-0 data-[state=closed]:scale-[0.98] transition-[opacity,transform] duration-[200ms] ease-[var(--ease-out)] focus:outline-none";

function DialogContentImpl(
  props: DialogContentProps,
  ref: ForwardedRef<ElementRef<typeof DialogPrimitive.Content>>,
): ReactElement {
  const { className, children, hideCloseButton = false, ...rest } = props;
  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(contentClasses, className)}
        {...rest}
      >
        {children}
        {!hideCloseButton ? (
          <DialogPrimitive.Close
            className="absolute right-4 top-4 inline-flex h-6 w-6 items-center justify-center rounded-md text-fg-muted hover:text-fg hover:bg-surface-2 focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-line-strong transition-colors duration-150"
            aria-label="Close"
          >
            <X size={14} weight="regular" />
          </DialogPrimitive.Close>
        ) : null}
      </DialogPrimitive.Content>
    </DialogPortal>
  );
}

export const DialogContent = forwardRef<
  ElementRef<typeof DialogPrimitive.Content>,
  DialogContentProps
>(DialogContentImpl);
DialogContent.displayName = "DialogContent";

export type DialogHeaderProps = HTMLAttributes<HTMLDivElement>;

export function DialogHeader(props: DialogHeaderProps): ReactElement {
  const { className, children, ...rest } = props;
  return (
    <div
      className={cn("flex flex-col gap-1.5 pb-4", className)}
      {...rest}
    >
      {children}
    </div>
  );
}

type DialogTitleProps = ComponentPropsWithoutRef<typeof DialogPrimitive.Title>;

function DialogTitleImpl(
  props: DialogTitleProps,
  ref: ForwardedRef<ElementRef<typeof DialogPrimitive.Title>>,
): ReactElement {
  const { className, children, ...rest } = props;
  return (
    <DialogPrimitive.Title
      ref={ref}
      className={cn("text-lg font-medium text-fg tracking-[-0.01em]", className)}
      {...rest}
    >
      {children}
    </DialogPrimitive.Title>
  );
}

export const DialogTitle = forwardRef<
  ElementRef<typeof DialogPrimitive.Title>,
  DialogTitleProps
>(DialogTitleImpl);
DialogTitle.displayName = "DialogTitle";

type DialogDescriptionProps = ComponentPropsWithoutRef<
  typeof DialogPrimitive.Description
>;

function DialogDescriptionImpl(
  props: DialogDescriptionProps,
  ref: ForwardedRef<ElementRef<typeof DialogPrimitive.Description>>,
): ReactElement {
  const { className, children, ...rest } = props;
  return (
    <DialogPrimitive.Description
      ref={ref}
      className={cn("text-sm text-fg-muted", className)}
      {...rest}
    >
      {children}
    </DialogPrimitive.Description>
  );
}

export const DialogDescription = forwardRef<
  ElementRef<typeof DialogPrimitive.Description>,
  DialogDescriptionProps
>(DialogDescriptionImpl);
DialogDescription.displayName = "DialogDescription";

export type DialogFooterProps = HTMLAttributes<HTMLDivElement>;

export function DialogFooter(props: DialogFooterProps): ReactElement {
  const { className, children, ...rest } = props;
  return (
    <div
      className={cn(
        "flex flex-col-reverse gap-2 pt-4 sm:flex-row sm:justify-end",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}
