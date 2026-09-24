"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import type { EventOut } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtSigned } from "@/lib/format";
import { EVENT_TYPE_LABEL, EVENT_TYPE_TONE, LEVEL_LABEL, LEVEL_TONE } from "@/lib/labels";
import { Badge, EmptyState, Table, Td, Th, cx } from "./ui";

export function EventTypeBadge({ type }: { type: string }) {
  return <Badge tone={EVENT_TYPE_TONE[type] ?? "gray"}>{EVENT_TYPE_LABEL[type] ?? type}</Badge>;
}

export function EventTable({ events, highlightId, showHotel = true }: { events: EventOut[]; highlightId?: number | null; showHotel?: boolean }) {
  const highlightRef = useRef<HTMLTableRowElement | null>(null);
  useEffect(() => {
    highlightRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlightId, events]);

  if (events.length === 0) return <EmptyState>Không có sự kiện nào trong khoảng đã chọn.</EmptyState>;
  return (
    <Table dense>
      <thead>
        <tr>
          <Th>Thời điểm</Th>
          <Th>Loại</Th>
          {showHotel && <Th>Khách sạn</Th>}
          <Th>Ngày lưu trú</Th>
          <Th>Loại phòng</Th>
          <Th>Từ → đến</Th>
          <Th right>Chênh lệch</Th>
          <Th>Tin cậy</Th>
        </tr>
      </thead>
      <tbody>
        {events.map((e) => {
          const hl = highlightId !== null && highlightId !== undefined && e.id === highlightId;
          return (
            <tr key={e.id} ref={hl ? highlightRef : undefined} className={cx(hl ? "bg-amber-50" : "hover:bg-slate-50")} id={`evt-${e.id}`}>
              <Td className="whitespace-nowrap text-slate-600">{fmtDateTime(e.observed_at)}</Td>
              <Td>
                <EventTypeBadge type={e.event_type} />
              </Td>
              {showHotel && (
                <Td>
                  <Link href={`/hotels/${e.hotel_id}`} className="text-sky-700 hover:underline">
                    {e.hotel_name ?? e.hotel_slug}
                  </Link>
                </Td>
              )}
              <Td className="whitespace-nowrap">
                <Link href={`/hotels/${e.hotel_id}/dates/${e.stay_date}`} className="text-sky-700 hover:underline">
                  {fmtDate(e.stay_date)}
                </Link>
              </Td>
              <Td>{e.room_type_name ?? <span className="text-slate-400">Mức khách sạn</span>}</Td>
              <Td className="whitespace-nowrap tabular">
                {e.from_value ?? "—"} → {e.to_value ?? "—"}
              </Td>
              <Td right>{fmtSigned(e.delta)}</Td>
              <Td>
                <Badge tone={LEVEL_TONE[e.confidence] ?? "gray"}>{LEVEL_LABEL[e.confidence] ?? e.confidence}</Badge>
              </Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}
