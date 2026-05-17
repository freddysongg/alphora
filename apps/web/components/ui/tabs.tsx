"use client";

import { createContext, forwardRef, useContext } from "react";
import type {
  ComponentPropsWithoutRef,
  ElementRef,
  ForwardedRef,
  ReactElement,
} from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { motion } from "framer-motion";
import { cn } from "@/lib/cn";

interface TabsActiveContextValue {
  activeValue: string;
}

const TabsActiveContext = createContext<TabsActiveContextValue | null>(null);

interface TabsProps
  extends Omit<
    ComponentPropsWithoutRef<typeof TabsPrimitive.Root>,
    "value" | "onValueChange" | "defaultValue"
  > {
  value: string;
  onValueChange: (next: string) => void;
}

export function Tabs(props: TabsProps): ReactElement {
  const { value, onValueChange, children, ...rest } = props;
  return (
    <TabsActiveContext.Provider value={{ activeValue: value }}>
      <TabsPrimitive.Root
        value={value}
        onValueChange={onValueChange}
        {...rest}
      >
        {children}
      </TabsPrimitive.Root>
    </TabsActiveContext.Provider>
  );
}

type TabsListProps = ComponentPropsWithoutRef<typeof TabsPrimitive.List>;

const listClasses = "relative flex items-end border-b border-line";

function TabsListImpl(
  props: TabsListProps,
  ref: ForwardedRef<ElementRef<typeof TabsPrimitive.List>>,
): ReactElement {
  const { className, children, ...rest } = props;
  return (
    <TabsPrimitive.List
      ref={ref}
      className={cn(listClasses, className)}
      {...rest}
    >
      {children}
    </TabsPrimitive.List>
  );
}

export const TabsList = forwardRef<
  ElementRef<typeof TabsPrimitive.List>,
  TabsListProps
>(TabsListImpl);
TabsList.displayName = "TabsList";

type TabsTriggerProps = ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>;

const triggerClasses =
  "relative text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted px-3 py-2 hover:text-fg focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-line-strong transition-colors duration-150 data-[state=active]:text-accent-text press-scale";

function TabsTriggerImpl(
  props: TabsTriggerProps,
  ref: ForwardedRef<ElementRef<typeof TabsPrimitive.Trigger>>,
): ReactElement {
  const { className, children, value, ...rest } = props;
  const context = useContext(TabsActiveContext);
  const isActive = context !== null && context.activeValue === value;
  return (
    <TabsPrimitive.Trigger
      ref={ref}
      value={value}
      className={cn(triggerClasses, className)}
      {...rest}
    >
      {children}
      {isActive ? (
        <motion.span
          aria-hidden="true"
          layoutId="nav-underline"
          transition={{ type: "spring", stiffness: 320, damping: 32 }}
          className="pointer-events-none absolute bottom-[-1px] left-2 right-2 h-[2px] bg-accent rounded-full"
        />
      ) : null}
    </TabsPrimitive.Trigger>
  );
}

export const TabsTrigger = forwardRef<
  ElementRef<typeof TabsPrimitive.Trigger>,
  TabsTriggerProps
>(TabsTriggerImpl);
TabsTrigger.displayName = "TabsTrigger";

type TabsContentProps = ComponentPropsWithoutRef<typeof TabsPrimitive.Content>;

function TabsContentImpl(
  props: TabsContentProps,
  ref: ForwardedRef<ElementRef<typeof TabsPrimitive.Content>>,
): ReactElement {
  const { className, ...rest } = props;
  return (
    <TabsPrimitive.Content
      ref={ref}
      className={cn(
        "pt-6 focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-line-strong",
        className,
      )}
      {...rest}
    />
  );
}

export const TabsContent = forwardRef<
  ElementRef<typeof TabsPrimitive.Content>,
  TabsContentProps
>(TabsContentImpl);
TabsContent.displayName = "TabsContent";
