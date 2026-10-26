"""Stable translation keys for curated parameters (ADR-Model-016).

The table is keyed by ParameterId, which equals the ValueId and is assigned by Wolf
per device template, not per installation: the wolf-comm example installation and the
owner's installation share every ID. Keys are a public interface for dashboards and
cards (README section "Translation keys"); they only change additively. A parameter
gets its key only on the platform it was curated for, otherwise it keeps the Wolf label.
"""

# ponytail: one row per observed ID (instance 1 of CHA, BM-2, MM1); a second mixer
# circuit or module needs its own rows with a _mixer_circuit_2 suffix.
TRANSLATION_KEYS: dict[str, dict[int, str]] = {
    "sensor": {
        27005000001: "operating_mode_heater",
        27005100001: "compressor_status",
        27004800001: "compressor_frequency",
        27001000001: "current_capacity_specification_compressor",
        27004900001: "power_consumption_wp_ehz",
        27005800001: "current_secondary_power",
        27000600001: "boiler_water_temperature",
        27000400001: "set_boiler_temperature",
        27000900001: "return_temperature",
        27002900001: "header_temperature",
        27002800001: "hc_flow_rate",
        27000500001: "outside_temperature",
        36000100001: "average_outside_temperature",
        27001300001: "3_way_diverter_valve_htg_dhw",
        27001400001: "3_way_diverter_valve_htg_clg",
        27001600001: "electric_booster_heater",
        27000700001: "dhw_temperature",
        27000800001: "set_dhw_temperature_adjusted",
        35000100000: "dhw_status",
        36001100001: "flow_temperature",
        4002700001: "mixer_flow_sensor_vf",
        36000500001: "mixer_circuit_status",
        36000400001: "mixer_circuit_demand",
        4000100001: "mkp_mixer_circuit_pump",
        4007000001: "mixer_circuit_pump",
        4000200001: "mixer_motor",
        27001100001: "heating_circuit_pump",
        27001200001: "feed_heating_circuit_pump",
        36000000001: "room_temperature",
        27003000001: "system_pressure",
        27002700001: "compressor_operating_hours",
        27003800001: "e_heating_operating_hours",
        27005900001: "energy_amount_htg",
        27006000001: "energy_amount_dhw",
        27006100001: "clg_energy_amount",
        27017600001: "heat_generated_previous_day",
        27016300001: "heat_generated_current_month",
        27016500001: "heat_generated_current_year",
        27016700001: "heat_generated_previous_year",
        27016900001: "heat_generated_year_before_last",
        27017500001: "consumption_previous_day",
        27016200001: "consumption_current_month",
        27016400001: "consumption_current_year",
        27016600001: "consumption_previous_year",
        27016800001: "consumption_year_before_last",
        27017200001: "jaz_current_year",
        27017300001: "jaz_previous_year",
        27017400001: "jaz_year_before_last",
        27017100001: "maz_current_month",
        27017700001: "taz_previous_day",
    },
    "number": {
        36008400001: "day_temperature_mixer_circuit_1",
        36006800001: "day_temperature_heating",
        35000900000: "set_dhw_temperature",
        36002900001: "setpoint_correction",
    },
    "select": {
        36005100001: "program_heating",
        35001200000: "program_dhw",
        36001600001: "time_program_heating",
        35000400000: "time_program_dhw",
    },
    "switch": {
        22004200000: "one_time_dhw_charge",
    },
}
