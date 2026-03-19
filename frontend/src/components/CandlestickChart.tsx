"use client";

import {
  createChart,
  IChartApi,
  ISeriesApi,
  IPriceLine,
  LineStyle,
  ColorType,
  CandlestickData,
  UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { Candle, ExecutionLevels } from "@/lib/types";

interface Props {
  candles: Candle[];
  executionLevels?: ExecutionLevels | null;
  height?: number;
  isLoading?: boolean;
}

export default function CandlestickChart({
  candles,
  executionLevels,
  height = 420,
  isLoading = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);

  // Mount chart once
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#18181b" },
        textColor: "#a1a1aa",
        fontFamily: "'JetBrains Mono', 'IBM Plex Mono', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#27272a" },
        horzLines: { color: "#27272a" },
      },
      crosshair: {
        vertLine: { color: "#52525b", labelBackgroundColor: "#3f3f46" },
        horzLine: { color: "#52525b", labelBackgroundColor: "#3f3f46" },
      },
      rightPriceScale: {
        borderColor: "#3f3f46",
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      timeScale: {
        borderColor: "#3f3f46",
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, axisPressedMouseMove: true },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const observer = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.resize(containerRef.current.clientWidth, height);
      }
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [height]);

  // Update candle data
  useEffect(() => {
    if (!seriesRef.current || candles.length === 0) return;

    const data: CandlestickData[] = candles
      .map((c) => ({
        time: Math.floor(c.ts / 1000) as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
      .sort((a, b) => (a.time as number) - (b.time as number));

    seriesRef.current.setData(data);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // Update execution level lines
  useEffect(() => {
    if (!seriesRef.current) return;

    // Remove existing price lines
    priceLinesRef.current.forEach((pl) => seriesRef.current?.removePriceLine(pl));
    priceLinesRef.current = [];

    if (!executionLevels) return;

    const lines: Array<{ price: number | null; color: string; style: LineStyle; title: string }> =
      [
        {
          price: executionLevels.entry,
          color: "#3b82f6",
          style: LineStyle.Dashed,
          title: "Entry",
        },
        {
          price: executionLevels.stop,
          color: "#ef4444",
          style: LineStyle.Solid,
          title: "Stop",
        },
        {
          price: executionLevels.target,
          color: "#22c55e",
          style: LineStyle.Solid,
          title: "Target",
        },
      ];

    lines.forEach(({ price, color, style, title }) => {
      if (price == null || !seriesRef.current) return;
      const pl = seriesRef.current.createPriceLine({
        price,
        color,
        lineWidth: 1,
        lineStyle: style,
        axisLabelVisible: true,
        title,
      });
      priceLinesRef.current.push(pl);
    });
  }, [executionLevels]);

  if (isLoading) {
    return (
      <div
        className="skeleton"
        style={{ height, borderRadius: "4px" }}
        aria-label="Loading chart..."
      />
    );
  }

  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: "4px",
        overflow: "hidden",
        background: "#18181b",
      }}
    >
      <div ref={containerRef} style={{ height }} />
      {candles.length === 0 && (
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{ color: "var(--text-dim)" }}
        >
          <span className="font-mono text-xs">NO DATA</span>
        </div>
      )}
    </div>
  );
}
