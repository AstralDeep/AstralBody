import json
from astralprims import *
import astralprims

F = {}
F["button_doctest"] = Button(label="Click me", action="open", css={"background-color": "white", "color": "#000000"}).to_dict()
F["text_variant"] = Text(content="Hello **md**", variant="h2", id="t1", tooltip="tip").to_dict()
F["container_nested"] = Container(direction="row").add(
    Card(title="Welcome", content=[Button(label="Get started", action="go")]),
    Divider()).to_dict()
F["card_variant"] = Card(title="KPIs", variant="elevated", class_name="wide", content=[
    MetricCard(title="Revenue", value="$1.2M", subtitle="+12%", icon="📈", variant="success", progress=0.72)]).to_dict()
F["grid"] = Grid(columns=3, gap=12).add(Text(content="a"), Text(content="b")).to_dict()
F["tabs"] = Tabs(tabs=[
    TabItem(label="One", content=[Text(content="first")], value="one"),
    TabItem(label="Two", content=[Alert(message="careful", variant="warning", title="Heads up")])],
    variant="pills").to_dict()
F["collapsible"] = Collapsible(title="Details", default_open=True, content=[
    CodeBlock(code="print('hi')", language="python", show_line_numbers=True)]).to_dict()
F["divider"] = Divider(variant="dashed").to_dict()
F["input"] = Input(placeholder="Type...", name="q", value="seed").to_dict()
F["param_picker"] = ParamPicker(title="Train", description="Pick params",
    fields=[{"name": "epochs", "label": "Epochs", "kind": "number", "default": 3, "step": 1}],
    submit_label="Go", submit_message_template="Train with {epochs}").to_dict()
F["image"] = Image(url="https://x/y.png", alt="alt", width="320", height="200").to_dict()
F["alert"] = Alert(message="ok", variant="success").to_dict()
F["progress"] = ProgressBar(value=0.4, label="Loading", variant="info", show_percentage=False).to_dict()
F["list_mixed"] = List_(items=["a", {"label": "b", "hint": "h"}], ordered=True, variant="compact").to_dict()
F["table_paginated"] = Table(headers=["City", "Pop"], rows=[["NYC", 8.3], ["LA", 3.9]],
    total_rows=12, page_size=2, page_offset=0, page_sizes=[2, 5],
    source_tool="cities", source_agent="demo-1", source_params={"country": "US"}).to_dict()
F["bar_chart"] = BarChart(title="Bars", labels=["a", "b"],
    datasets=[ChartDataset(label="s1", data=[1, 2], color="#fff").model_dump()]).to_dict()
F["line_chart"] = LineChart(title="Lines", labels=["t1"], datasets=[{"label": "s", "data": [3.5]}]).to_dict()
F["pie_chart"] = PieChart(title="Pie", labels=["x", "y"], data=[60, 40], colors=["#111", "#222"]).to_dict()
F["plotly_chart"] = PlotlyChart(title="P", data=[{"y": [1, 2, 3], "type": "scatter"}],
    layout={"height": 300}, config={"displayModeBar": False}).to_dict()
F["audio"] = Audio(src="data:audio/wav;base64,AAA", contentType="audio/wav", autoplay=True,
    loop=False, label="Clip", showControls=True, description="desc").to_dict()
F["file_upload"] = FileUpload(label="Up", accept=".csv", action="upload_csv").to_dict()
F["file_download"] = FileDownload(label="Get", url="/f.txt", filename="f.txt").to_dict()
F["badge"] = Badge(label="LIVE", variant="accent", icon="!").to_dict()
F["hero"] = Hero(title="Q3", subtitle="sub", eyebrow="REPORT", icon="R", variant="gradient",
    badges=["A", "B"]).to_dict()
F["keyvalue"] = KeyValue(title="Facts", items=[{"label": "Owner", "value": "P&B", "hint": "since 2021"}],
    columns=1).to_dict()
F["timeline"] = Timeline(title="Day", items=[{"time": "9:00", "title": "Groom", "variant": "success"}],
    variant="default").to_dict()
F["rating"] = Rating(value=4.5, max_value=5, label="CSAT", subtitle="n=100", show_value=True).to_dict()
F["chat_history"] = ChatHistory(items=[{"chat_id": "c1", "title": "Weather"}]).to_dict()
F["color_picker"] = ColorPicker(label="Primary", color_key="primary", value="#6366F1").to_dict()
F["theme_apply"] = ThemeApply(preset="ocean", message="Applied").to_dict()
F["metric_minimal"] = MetricCard().to_dict()
F["attributes_override"] = Text(content="x", attributes={"variant": "h1", "data-test": "1"}).to_dict()
F["envelope"] = create_ui_response([Text(content="hi"), Badge(label="ok")])

with open("/tmp/fixtures_out.json", "w") as f:
    json.dump({"astralprims_version": astralprims.__version__, "fixtures": F}, f, ensure_ascii=False, indent=1, sort_keys=True)
print("wrote", len(F), "fixtures")
