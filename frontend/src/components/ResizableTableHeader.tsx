import { PointerEvent, ReactNode, useState } from "react";

interface ResizableTableHeaderProps {
  children: ReactNode;
  initialWidth: number;
  align?: "left" | "right";
}

export function ResizableTableHeader({
  children,
  initialWidth,
  align = "left",
}: ResizableTableHeaderProps) {
  const [width, setWidth] = useState(initialWidth);

  function startResize(event: PointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;
    const move = (moveEvent: globalThis.PointerEvent) => {
      setWidth(Math.max(80, startWidth + moveEvent.clientX - startX));
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  }

  return (
    <th
      scope="col"
      className={`relative p-3 ${align === "right" ? "text-right" : "text-left"}`}
      style={{ width, minWidth: width }}
    >
      {children}
      <button
        type="button"
        aria-label={`Ridimensiona colonna ${String(children)}`}
        className="absolute inset-y-0 right-0 w-2 cursor-col-resize touch-none border-r border-transparent hover:border-primary focus:border-primary focus:outline-none"
        onPointerDown={startResize}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            setWidth((current) => Math.max(80, current + (event.key === "ArrowRight" ? 16 : -16)));
          }
          if (event.key === "Home") {
            event.preventDefault();
            setWidth(initialWidth);
          }
        }}
        title="Frecce sinistra/destra per ridimensionare; Home per ripristinare"
      />
    </th>
  );
}
