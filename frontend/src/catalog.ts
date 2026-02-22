/**
 * json-render catalog — defines all UI component types the backend can generate.
 * Maps 1:1 with backend shared/primitives.py component types.
 */
import { defineCatalog } from "@json-render/core";
import { schema } from "@json-render/react";
import { z } from "zod";

export const catalog = defineCatalog(schema, {
    components: {
        container: {
            props: z.object({
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "A flex container with children",
        },
        text: {
            props: z.object({
                content: z.string(),
                variant: z.enum(["h1", "h2", "h3", "body", "caption"]).optional(),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "Text display with variant styling",
        },
        card: {
            props: z.object({
                title: z.string(),
                variant: z.string().optional(),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "A card container with title and children content",
        },
        table: {
            props: z.object({
                headers: z.array(z.string()),
                rows: z.array(z.array(z.any())),
                variant: z.string().optional(),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "Data table with headers and rows",
        },
        metric: {
            props: z.object({
                title: z.string(),
                value: z.string(),
                subtitle: z.string().nullable().optional(),
                icon: z.string().nullable().optional(),
                progress: z.number().nullable().optional(),
                variant: z.string().optional(),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "Metric card showing a KPI value with optional progress",
        },
        alert: {
            props: z.object({
                message: z.string(),
                title: z.string().nullable().optional(),
                variant: z.enum(["info", "success", "warning", "error"]).optional(),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "Alert/notification banner",
        },
        progress: {
            props: z.object({
                value: z.number(),
                label: z.string().nullable().optional(),
                show_percentage: z.boolean().optional(),
                variant: z.string().optional(),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "Progress bar",
        },
        grid: {
            props: z.object({
                columns: z.number().optional(),
                gap: z.number().optional(),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "Grid layout with children",
        },
        list: {
            props: z.object({
                items: z.array(z.any()),
                ordered: z.boolean().optional(),
                variant: z.string().optional(),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "List of items",
        },
        code: {
            props: z.object({
                code: z.string(),
                language: z.string().optional(),
                show_line_numbers: z.boolean().optional(),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "Code block with syntax highlighting",
        },
        bar_chart: {
            props: z.object({
                title: z.string(),
                labels: z.array(z.string()),
                datasets: z.array(z.any()),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "Bar chart visualization",
        },
        line_chart: {
            props: z.object({
                title: z.string(),
                labels: z.array(z.string()),
                datasets: z.array(z.any()),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "Line chart visualization",
        },
        pie_chart: {
            props: z.object({
                title: z.string(),
                labels: z.array(z.string()),
                data: z.array(z.number()),
                colors: z.array(z.string()).optional(),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "Pie chart visualization",
        },
        divider: {
            props: z.object({
                variant: z.string().optional(),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "Visual divider/separator",
        },
        button: {
            props: z.object({
                label: z.string(),
                action: z.string().optional(),
                variant: z.string().optional(),
                id: z.string().nullable().optional(),
                style: z.record(z.string(), z.string()).optional(),
            }),
            description: "Clickable button",
        },
    },
    actions: {
        chat_message: { description: "Send a chat message" },
        tool_action: { description: "Invoke a tool action" },
    },
});
