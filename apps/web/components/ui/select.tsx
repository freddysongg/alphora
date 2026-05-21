"use client";

import { forwardRef } from "react";
import type {
  ComponentPropsWithoutRef,
  ElementRef,
  ForwardedRef,
  ReactElement,
  ReactNode,
} from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { CaretDown, Check } from "@phosphor-icons/react/dist/ssr";
import { cn } from "@/lib/cn";

export const Select = SelectPrimitive.Root;
export const SelectGroup = SelectPrimitive.Group;
export const SelectValue = SelectPrimitive.Value;

type SelectTriggerProps = ComponentPropsWithoutRef<
  typeof SelectPrimitive.Trigger
>;

const triggerClasses =
  "inline-flex h-9 w-full items-center justify-between gap-2 rounded-md bg-[#14121f] border border-[#2a2440] px-3 text-sm text-fg placeholder:text-fg-subtle hover:bg-[#1a1525] hover:border-[#3a2f50] focus:border-[#7a4dff] focus:outline-none transition-[background-color,border-color] duration-150 disabled:opacity-50 disabled:cursor-not-allowed data-[state=open]:border-[#7a4dff] data-[state=open]:bg-[#1a1525]";

function SelectTriggerImpl(
  props: SelectTriggerProps,
  ref: ForwardedRef<ElementRef<typeof SelectPrimitive.Trigger>>,
): ReactElement {
  const { className, children, ...rest } = props;
  return (
    <SelectPrimitive.Trigger
      ref={ref}
      className={cn(triggerClasses, className)}
      {...rest}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <CaretDown size={14} weight="regular" className="text-fg-muted" />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}

export const SelectTrigger = forwardRef<
  ElementRef<typeof SelectPrimitive.Trigger>,
  SelectTriggerProps
>(SelectTriggerImpl);
SelectTrigger.displayName = "SelectTrigger";

type SelectContentProps = ComponentPropsWithoutRef<
  typeof SelectPrimitive.Content
>;

const contentClasses =
  "z-50 min-w-[10rem] overflow-hidden rounded-md bg-[#14121f] border border-[#2a2440] shadow-[var(--shadow-popover)] origin-[var(--radix-select-content-transform-origin)] data-[state=open]:opacity-100 data-[state=open]:scale-100 data-[state=closed]:opacity-0 data-[state=closed]:scale-[0.97] transition-[opacity,transform] duration-[200ms] ease-[var(--ease-out)]";

function SelectContentImpl(
  props: SelectContentProps,
  ref: ForwardedRef<ElementRef<typeof SelectPrimitive.Content>>,
): ReactElement {
  const { className, children, position = "popper", ...rest } = props;
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        ref={ref}
        position={position}
        className={cn(
          contentClasses,
          position === "popper" && "data-[side=bottom]:translate-y-1",
          className,
        )}
        {...rest}
      >
        <SelectPrimitive.Viewport className="p-1">
          {children}
        </SelectPrimitive.Viewport>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
}

export const SelectContent = forwardRef<
  ElementRef<typeof SelectPrimitive.Content>,
  SelectContentProps
>(SelectContentImpl);
SelectContent.displayName = "SelectContent";

type SelectItemProps = ComponentPropsWithoutRef<typeof SelectPrimitive.Item>;

const itemClasses =
  "relative flex h-8 cursor-pointer select-none items-center rounded-[6px] pl-4 pr-8 text-sm text-fg-muted outline-none hover:bg-[#1a1525] hover:text-fg focus:bg-[#1a1525] focus:text-fg data-[state=checked]:text-accent-text data-[state=checked]:before:absolute data-[state=checked]:before:left-0 data-[state=checked]:before:top-1 data-[state=checked]:before:bottom-1 data-[state=checked]:before:w-[2px] data-[state=checked]:before:bg-accent data-[state=checked]:before:rounded-sm data-[disabled]:opacity-50 data-[disabled]:pointer-events-none";

function SelectItemImpl(
  props: SelectItemProps,
  ref: ForwardedRef<ElementRef<typeof SelectPrimitive.Item>>,
): ReactElement {
  const { className, children, ...rest } = props;
  return (
    <SelectPrimitive.Item
      ref={ref}
      className={cn(itemClasses, className)}
      {...rest}
    >
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      <span className="absolute right-2 flex h-4 w-4 items-center justify-center">
        <SelectPrimitive.ItemIndicator>
          <Check size={12} weight="regular" className="text-accent" />
        </SelectPrimitive.ItemIndicator>
      </span>
    </SelectPrimitive.Item>
  );
}

export const SelectItem = forwardRef<
  ElementRef<typeof SelectPrimitive.Item>,
  SelectItemProps
>(SelectItemImpl);
SelectItem.displayName = "SelectItem";

type SelectLabelProps = ComponentPropsWithoutRef<typeof SelectPrimitive.Label>;

function SelectLabelImpl(
  props: SelectLabelProps,
  ref: ForwardedRef<ElementRef<typeof SelectPrimitive.Label>>,
): ReactElement {
  const { className, children, ...rest } = props;
  return (
    <SelectPrimitive.Label
      ref={ref}
      className={cn(
        "px-2 py-1.5 text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted",
        className,
      )}
      {...rest}
    >
      {children as ReactNode}
    </SelectPrimitive.Label>
  );
}

export const SelectLabel = forwardRef<
  ElementRef<typeof SelectPrimitive.Label>,
  SelectLabelProps
>(SelectLabelImpl);
SelectLabel.displayName = "SelectLabel";

type SelectSeparatorProps = ComponentPropsWithoutRef<
  typeof SelectPrimitive.Separator
>;

function SelectSeparatorImpl(
  props: SelectSeparatorProps,
  ref: ForwardedRef<ElementRef<typeof SelectPrimitive.Separator>>,
): ReactElement {
  const { className, ...rest } = props;
  return (
    <SelectPrimitive.Separator
      ref={ref}
      className={cn("my-1 h-px bg-line", className)}
      {...rest}
    />
  );
}

export const SelectSeparator = forwardRef<
  ElementRef<typeof SelectPrimitive.Separator>,
  SelectSeparatorProps
>(SelectSeparatorImpl);
SelectSeparator.displayName = "SelectSeparator";
