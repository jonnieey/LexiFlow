from typing import Any, Dict, List, Tuple, Union


def parse_conditions_as_dict(condition_strings: List[str]) -> Dict[str, str]:
    """
    input = ['name=anderson', 'id<=1', 'amount>0']
    output = {'name': 'anderson', 'id': 1, 'amount': '0' }
    """
    conditions_dict = {}
    for condition_string in condition_strings:
        field, value = condition_string.split("=")
        conditions_dict[field] = value
    return conditions_dict


def parse_conditions(
    condition_strings: List[str],
) -> Dict[str, Union[List[Tuple[str, str]], List[Tuple[str, int]]]]:
    """
    Parses a list of condition strings and returns a dictionary.

    Args:
        condition_strings: A list of strings representing conditions like "id<=1", "amount>0".

    Returns:
        A dictionary where keys are field names (e.g., "id", "amount") and values are
        lists of tuples, each tuple containing an operator and a value.
        For example: {"id": [("<=", 1)], "amount": [(">", 0), ("<", 10)]}
    """
    conditions_dict: Dict[str, List[Tuple[str, Any]]] = {}
    operators = {
        "<=": "<=",
        ">=": ">=",
        "!=": "!=",
        "<": "<",
        ">": ">",
        "==": "=",
        "=": "==",
        "~": "~",
    }

    for condition_str in condition_strings:
        parsed = False
        for op_symbol, op_name in operators.items():
            if op_symbol in condition_str:
                parts = condition_str.split(op_symbol, 1)  # Split only once
                if len(parts) == 2:
                    field = parts[0].strip()
                    value_str = parts[1].strip()
                    try:
                        value = type_convert(
                            value_str
                        )  # Try to convert value to int or float, otherwise keep as string
                        if field:  # Ensure field name is not empty
                            if field not in conditions_dict:
                                conditions_dict[field] = []
                            conditions_dict[field].append((op_name, value))
                            parsed = True
                            break  # Stop checking operators after finding one
                    except ValueError:
                        if field:
                            if field not in conditions_dict:
                                conditions_dict[field] = []
                            conditions_dict[field].append(
                                (op_name, value_str)
                            )
                            parsed = True
                            break
        if not parsed:
            # Using print as a warning here, but standard logging would be better
            print(
                f"Warning: Could not parse condition string: '{condition_str}'. Ensure it is in the format 'field[operator]value'."
            )

    return conditions_dict


def type_convert(value_str: str) -> Union[str, int, float]:
    """
    Attempts to convert a string to an int or float. If it fails, returns the string as is.
    """
    try:
        return int(value_str)
    except ValueError:
        try:
            return float(value_str)
        except ValueError:
            return value_str  # Return as string if not int or float


def parse_sql_clause(sql_clause, split_by):
    condition_list = sql_clause.split(split_by)
    condition_dict = {}

    for condition in condition_list:
        parts = condition.split("=")
        if len(parts) != 2:
            continue
        column, value = parts
        column = column.strip()
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')):
            value = value[1:-1]
        condition_dict[column] = value

    return condition_dict


def parse_sql_update_query(sql_query):
    set_clause_start = sql_query.upper().find("SET") + len("SET")
    where_clause_start = sql_query.upper().find("WHERE")

    if where_clause_start == -1:
        where_clause_start = len(sql_query)

    set_clause = sql_query[set_clause_start:where_clause_start].strip()
    set_assignments = parse_sql_clause(set_clause, ",")

    where_assignments = {}
    if where_clause_start < len(sql_query):
        where_clause = sql_query[where_clause_start + len("WHERE") :].strip()
        where_assignments = parse_sql_clause(where_clause, "AND")

    return set_assignments, where_assignments
