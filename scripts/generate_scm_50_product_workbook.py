"""Generate a realistic, deterministic SCM end-to-end import workbook."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo


OUTPUT = Path(__file__).resolve().parents[1] / "test-data" / "SCM_50_Product_End_to_End_Test.xlsx"
NOW = datetime.now(timezone.utc).replace(microsecond=0)
TODAY = NOW.date()

SHEETS = {
    "Materials": ["external_id", "material_code", "description", "material_type", "base_uom", "specification_text"],
    "MaterialPlantPolicies": ["external_id", "material_code", "planned_lead_time_days", "goods_receipt_processing_days", "safety_stock_qty", "minimum_order_qty", "order_multiple", "minimum_coverage_days", "maximum_coverage_days", "planning_time_fence_days", "cancellation_window_days", "expedite_window_days", "procurement_type"],
    "Customers": ["external_id", "customer_code", "name"],
    "CustomerUsage": ["external_id", "finished_good_code", "customer_code", "program_name", "customer_part_number"],
    "BOMs": ["external_id", "bom_code", "revision", "parent_material_code", "effective_from", "effective_to", "status"],
    "BOMLines": ["external_id", "bom_code", "revision", "line_number", "component_material_code", "quantity_per", "uom", "scrap_factor"],
    "Inventory": ["external_id", "material_code", "snapshot_at", "on_hand_qty", "available_qty", "uom"],
    "Forecasts": ["external_id", "material_code", "forecast_version", "bucket_start", "bucket_end", "quantity", "uom", "forecast_type"],
    "Requirements": ["external_id", "material_code", "required_date", "quantity", "uom", "requirement_type", "priority", "finished_good_code", "customer_code"],
    "SupplyOrders": ["external_id", "material_code", "supply_type", "order_number", "line_number", "ordered_qty", "received_qty", "uom", "status", "firmness", "supplier_code"],
    "SupplySchedules": ["external_id", "supply_order_external_id", "schedule_line_number", "scheduled_qty", "received_qty", "original_due_date", "current_due_date", "status"],
    "GoodsReceipts": ["external_id", "material_code", "receipt_date", "quantity", "uom", "supply_order_external_id"],
}


def iso(day_offset: int) -> str:
    return (TODAY + timedelta(days=day_offset)).isoformat()


def rows() -> dict[str, list[list[object]]]:
    result = {name: [] for name in SHEETS}
    customers = [
        ("CUST-AUTO-01", "TITAN-MOTORS", "Titan Motors India"),
        ("CUST-AUTO-02", "NOVA-EV", "Nova Electric Mobility"),
        ("CUST-AUTO-03", "ORBIT-TRUCK", "Orbit Commercial Vehicles"),
        ("CUST-AUTO-04", "APEX-OEM", "Apex Automotive Systems"),
        ("CUST-AUTO-05", "VELOCITY", "Velocity Two Wheelers"),
    ]
    result["Customers"].extend(customers)

    fg_names = ["Smart headlamp controller", "EV battery junction unit", "Digital instrument cluster",
        "Body control module", "Telematics gateway", "Motor inverter controller", "Seat control module",
        "ADAS sensor hub", "Vehicle power distribution unit", "Thermal management controller"]
    component_names = ["Automotive PCB assembly", "Aluminium die-cast housing", "Sealed connector set", "Power MOSFET module",
        "Microcontroller IC", "Current sensor", "EMI filter choke", "Thermal interface pad", "Injection moulded cover",
        "Copper busbar", "CAN transceiver", "High-current relay", "Ceramic capacitor bank", "Precision shunt resistor",
        "Wiring pigtail", "Stainless mounting bracket", "Silicone gasket", "Heat sink extrusion", "EEPROM memory IC",
        "Voltage regulator", "LED driver IC", "Optical light guide", "Lens carrier", "FR4 control board",
        "Board-to-board connector", "Automotive fuse", "Pressure equalization vent", "Laser-marked label",
        "M4 flange bolt", "Spring washer", "Shielding can", "Hall-effect sensor", "NTC temperature sensor",
        "Fan blower assembly", "Coolant valve actuator", "ABS enclosure", "Terminal blade set", "Potting compound",
        "Conformal coating", "Packaging tray"]

    for number, name in enumerate(fg_names, 1):
        code = f"GG-FG-{number:03d}"
        result["Materials"].append([f"ERP-MAT-{code}", code, name, "FINISHED_GOOD", "EA", f"Automotive grade assembly; revision {chr(64+number)}"])
        result["MaterialPlantPolicies"].append([f"POL-{code}", code, 7, 1, 40, 20, 10, 5, 35, 3, 7, 10, "MAKE"])
        customer = customers[(number - 1) % len(customers)]
        result["CustomerUsage"].append([f"USAGE-{code}", code, customer[1], f"2027 Vehicle Program {number}", f"OEM-{number:03d}-{code[-3:]}"])
        bom = f"BOM-{code}"
        result["BOMs"].append([f"ERP-{bom}-A", bom, "A", code, iso(-365), "", "ACTIVE"])
        for position in range(4):
            component_number = (number - 1) * 4 + position + 1
            component = f"GG-CMP-{component_number:03d}"
            result["BOMLines"].append([f"ERP-{bom}-{(position+1)*10}", bom, "A", (position+1)*10,
                component, [1, 2, 4, 1][position], "EA", [0.01, 0.02, 0.005, 0][position]])
        result["Inventory"].append([f"INV-{code}-{TODAY:%Y%m%d}", code, NOW.isoformat().replace("+00:00", "Z"), 420 + number*20, 400 + number*20, "EA"])
        demand_day = 14 + number
        result["Requirements"].append([f"REQ-{code}-01", code, iso(demand_day), 160 + number*8, "EA", "CUSTOMER_ORDER", 10,
            "", customer[1]])
        result["Forecasts"].append([f"FCST-{code}-M1", code, "SOP-2026.08", iso(31), iso(60), 240 + number*10, "EA", "BASELINE"])

    for number, name in enumerate(component_names, 1):
        code = f"GG-CMP-{number:03d}"
        result["Materials"].append([f"ERP-MAT-{code}", code, name, "COMPONENT", "EA", "IATF-oriented production component"])
        lead = 7 + (number % 5) * 4
        result["MaterialPlantPolicies"].append([f"POL-{code}", code, lead, 1, 100 + number*5, 250, 50, 7, 45, 4, 7, 14, "BUY"])
        fg_number = ((number - 1) // 4) + 1
        fg = f"GG-FG-{fg_number:03d}"
        customer = customers[(fg_number - 1) % len(customers)][1]

        if number <= 8:  # critical: receipt occurs after stockout
            available, demand, due, current_due, supply = 180 + number*5, 1100 + number*20, 7, 22, 900
        elif number <= 16:  # watch: narrow coverage gap
            available, demand, due, current_due, supply = 650 + number*4, 1000, 15, 17, 700
        elif number <= 28:  # healthy: supply precedes demand
            available, demand, due, current_due, supply = 1350 + number*10, 900, 24, 12, 800
        elif number <= 34:  # excess inventory
            available, demand, due, current_due, supply = 6500 + number*25, 500, 35, 18, 3000
        elif number <= 38:  # supplier delay from day 8 to day 27
            available, demand, due, current_due, supply = 450, 1300, 10, 27, 1200
        else:  # exposed demand with no confirmed supply
            available, demand, due, current_due, supply = 120, 1400, 9, None, 0

        result["Inventory"].append([f"INV-{code}-{TODAY:%Y%m%d}", code, NOW.isoformat().replace("+00:00", "Z"), available + 50, available, "EA"])
        result["Requirements"].append([f"REQ-{code}-01", code, iso(due), demand, "EA", "PRODUCTION", 20, fg, customer])
        result["Forecasts"].append([f"FCST-{code}-M1", code, "SOP-2026.08", iso(31), iso(60), round(demand*0.65), "EA", "BASELINE"])
        if current_due is not None:
            po = f"ERP-PO-{number:04d}"
            result["SupplyOrders"].append([po, code, "PURCHASE_ORDER", f"4500{number:06d}", "10", supply, 0, "EA", "OPEN", "FIRM", ""])
            original_due = 8 if 35 <= number <= 38 else current_due
            result["SupplySchedules"].append([f"SCH-{number:04d}-1", po, "1", supply, 0, iso(original_due), iso(current_due), "CONFIRMED"])
            if number in {17, 18, 29, 30, 35}:
                receipt = min(100, supply)
                result["GoodsReceipts"].append([f"GR-{number:04d}-1", code, iso(-2), receipt, "EA", po])
    return result


def style(workbook: Workbook) -> None:
    dark, pale, white = "063C35", "E9F4F0", "FFFFFF"
    thin = Side(style="thin", color="DCE5E2")
    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.sheet_view.showGridLines = False
        for cell in sheet[1]:
            cell.fill = PatternFill("solid", fgColor=dark)
            cell.font = Font(color=white, bold=True)
            cell.alignment = Alignment(vertical="center")
        sheet.row_dimensions[1].height = 27
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.fill = PatternFill("solid", fgColor=pale if cell.row % 2 == 0 else white)
                cell.border = Border(bottom=thin)
                cell.alignment = Alignment(vertical="center")
        for column in sheet.columns:
            values = [str(cell.value or "") for cell in column[:100]]
            sheet.column_dimensions[column[0].column_letter].width = min(max(max(map(len, values)) + 2, 12), 38)
        if sheet.max_row > 1:
            table = Table(displayName=f"tbl{sheet.title.replace(' ', '')}", ref=sheet.dimensions)
            table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium4", showRowStripes=True, showFirstColumn=False)
            sheet.add_table(table)
    inventory = workbook["Inventory"]
    inventory.conditional_formatting.add(f"E2:E{inventory.max_row}",
        ColorScaleRule(start_type="min", start_color="F8696B", mid_type="percentile", mid_value=50,
                       mid_color="FFEB84", end_type="max", end_color="63BE7B"))


def build() -> Path:
    workbook = Workbook()
    workbook.remove(workbook.active)
    data = rows()
    for name, headers in SHEETS.items():
        sheet = workbook.create_sheet(name)
        sheet.append(headers)
        for row in data[name]:
            sheet.append(row)
    style(workbook)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(OUTPUT)
    # Re-open as a corruption guard and verify the principal test cardinality.
    check = load_workbook(OUTPUT, read_only=True, data_only=False)
    assert check["Materials"].max_row - 1 == 50
    assert set(SHEETS).issubset(check.sheetnames)
    return OUTPUT


if __name__ == "__main__":
    print(build())
