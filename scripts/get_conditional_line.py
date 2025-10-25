import ast
from typing import List, Set, Dict, Optional, Tuple
from collections import defaultdict

class DynamicSlicer:
    """
    Implements Agrawal and Horgan's dynamic backward slicing algorithm (Approach 2)
    with inter-procedural extensions for Python code.
    """
    def __init__(self):
        # Phase 1: Execution tracking and PDG/SDG construction
        self.executed_statements = set()  # Marked statements from execution
        self.executed_dependencies = set()  # Marked dependencies from execution
        self.pdgs = {}  # function_name -> PDG (Program Dependence Graph)
        self.sdg = {}  # System Dependence Graph (inter-procedural)
        
        # Phase 2: Slicing phase
        self.slice_nodes = set()  # Nodes in the resulting slice
        self.def_use_relations = defaultdict(set)  # variable -> set of (def_line, use_line)
        self.info_flow_relations = defaultdict(set)  # variable -> set of (ref_line, def_line)
        
    def compute_dynamic_slice(self, code: str, target_line: int, executed_lines: Set[int] = None) -> List[int]:
        """
        Compute dynamic backward slice using Agrawal and Horgan's algorithm.
        
        Phase 1: Build PDGs and SDG, mark executed statements and dependencies
        Phase 2: Traverse backward along marked nodes and edges only
        
        Args:
            code: Python source code as string
            target_line: Line number to analyze (1-based)
            executed_lines: Set of line numbers that were executed (if None, assumes all lines)
            
        Returns:
            List of line numbers in the dynamic backward slice
        """
        try:
            tree = ast.parse(code)
            
            # Phase 1: Build static program dependence graphs and mark executed elements
            self._build_pdgs_and_sdg(tree)
            if executed_lines is None:
                # If no execution info provided, assume all statements were executed
                executed_lines = self._get_all_statement_lines(tree)
            self._mark_executed_elements(executed_lines)
            
            # Phase 2: Compute dynamic slice by traversing marked dependencies
            self._compute_dynamic_slice(target_line)
            
            return sorted(list(self.slice_nodes))
            
        except SyntaxError as e:
            raise ValueError(f"Invalid Python code: {e}")
    
    def _get_all_statement_lines(self, tree: ast.AST) -> Set[int]:
        """Get all statement line numbers from the AST."""
        lines = set()
        for node in ast.walk(tree):
            if hasattr(node, 'lineno') and node.lineno is not None:
                lines.add(node.lineno)
        return lines
    
    def _build_pdgs_and_sdg(self, tree: ast.AST):
        """
        Phase 1: Build Program Dependence Graphs (PDGs) for all functions
        and construct System Dependence Graph (SDG) for inter-procedural slicing.
        """
        # Build PDG for the main module (module-level statements)
        self.pdgs['__main__'] = self._build_pdg_for_module(tree)
        
        # Build PDG for each function
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_name = node.name
                self.pdgs[func_name] = self._build_pdg_for_function(node)
        
        # Build SDG by linking PDGs through call sites and function entries
        self._build_sdg(tree)
    
    def _build_pdg_for_module(self, tree: ast.AST) -> Dict:
        """
        Build Program Dependence Graph for module-level statements.
        """
        pdg = {
            'control_deps': defaultdict(set),  # line -> set of controlling lines
            'data_deps': defaultdict(set),     # line -> set of data dependency lines
            'def_use': defaultdict(set),       # variable -> set of (def_line, use_line)
            'info_flow': defaultdict(set),     # variable -> set of (ref_line, def_line)
            'statements': set()                # all statement lines in module
        }
        
        # Track variable definitions and uses
        var_defs = {}  # variable -> line where defined
        var_uses = defaultdict(list)  # variable -> list of lines where used
        
        # Build control dependencies for module-level statements
        for node in tree.body:
            self._build_control_dependencies(node, set(), pdg['control_deps'])
            self._build_data_dependencies(node, var_defs, var_uses, pdg)
        
        # Collect all statement lines
        for node in ast.walk(tree):
            if hasattr(node, 'lineno') and node.lineno is not None:
                pdg['statements'].add(node.lineno)
        
        return pdg
    
    def _build_pdg_for_function(self, func_node: ast.FunctionDef) -> Dict:
        """
        Build Program Dependence Graph for a single function.
        Returns a dictionary with control dependencies, data dependencies,
        and def-use relations.
        """
        pdg = {
            'control_deps': defaultdict(set),  # line -> set of controlling lines
            'data_deps': defaultdict(set),     # line -> set of data dependency lines
            'def_use': defaultdict(set),       # variable -> set of (def_line, use_line)
            'info_flow': defaultdict(set),     # variable -> set of (ref_line, def_line)
            'statements': set()                # all statement lines in function
        }
        
        # Track variable definitions and uses
        var_defs = {}  # variable -> line where defined
        var_uses = defaultdict(list)  # variable -> list of lines where used
        
        # Build control dependencies
        self._build_control_dependencies(func_node, set(), pdg['control_deps'])
        
        # Build data dependencies and def-use relations
        self._build_data_dependencies(func_node, var_defs, var_uses, pdg)
        
        # Collect all statement lines
        for node in ast.walk(func_node):
            if hasattr(node, 'lineno') and node.lineno is not None:
                pdg['statements'].add(node.lineno)
        
        return pdg
    
    def _build_control_dependencies(self, node: ast.AST, controlling_conditions: Set[int], 
                                  control_deps: Dict[int, Set[int]]):
        """Build control dependencies for a function."""
        # Record control dependencies for this node if it has a line number
        if hasattr(node, 'lineno') and node.lineno is not None:
            if controlling_conditions:
                control_deps[node.lineno] = controlling_conditions.copy()
        
        # Handle different control flow constructs
        if isinstance(node, ast.If):
            condition_line = node.lineno
            new_conditions = controlling_conditions | {condition_line}
            
            # Process if body
            for stmt in node.body:
                self._build_control_dependencies(stmt, new_conditions, control_deps)
            
            # Process elif/else
            all_if_conditions = controlling_conditions | {condition_line}
            self._handle_else_elif_chain(node.orelse, all_if_conditions, control_deps)
            
        elif isinstance(node, ast.While):
            condition_line = node.lineno
            new_conditions = controlling_conditions | {condition_line}
            
            for stmt in node.body:
                self._build_control_dependencies(stmt, new_conditions, control_deps)
            for stmt in node.orelse:
                self._build_control_dependencies(stmt, controlling_conditions, control_deps)
                
        elif isinstance(node, ast.For):
            condition_line = node.lineno
            new_conditions = controlling_conditions | {condition_line}
            
            for stmt in node.body:
                self._build_control_dependencies(stmt, new_conditions, control_deps)
            for stmt in node.orelse:
                self._build_control_dependencies(stmt, controlling_conditions, control_deps)
                
        elif isinstance(node, ast.Try):
            try_line = node.lineno
            new_conditions = controlling_conditions | {try_line}
            
            for stmt in node.body:
                self._build_control_dependencies(stmt, new_conditions, control_deps)
            
            for handler in node.handlers:
                handler_conditions = controlling_conditions | {handler.lineno}
                for stmt in handler.body:
                    self._build_control_dependencies(stmt, handler_conditions, control_deps)
            
            for stmt in node.orelse:
                self._build_control_dependencies(stmt, new_conditions, control_deps)
            for stmt in node.finalbody:
                self._build_control_dependencies(stmt, controlling_conditions, control_deps)
        
        elif isinstance(node, ast.Match):
            # Python 3.10+ structural pattern matching
            match_line = node.lineno
            base_conditions = controlling_conditions | {match_line}
            # Each case body is controlled by the match and optional guard
            for case in node.cases:
                case_conditions = set(base_conditions)
                guard = getattr(case, 'guard', None)
                if guard is not None and hasattr(guard, 'lineno') and guard.lineno is not None:
                    case_conditions.add(guard.lineno)
                for stmt in case.body:
                    self._build_control_dependencies(stmt, case_conditions, control_deps)
        
        elif isinstance(node, (ast.Break, ast.Continue)):
            # break and continue statements are controlled by their containing loop
            # They inherit control dependencies from their context
            if hasattr(node, 'lineno') and node.lineno is not None:
                if controlling_conditions:
                    control_deps[node.lineno] = controlling_conditions.copy()
            
        elif isinstance(node, ast.Return):
            # return statements are controlled by their containing function's control flow
            # They inherit control dependencies from their context
            if hasattr(node, 'lineno') and node.lineno is not None:
                if controlling_conditions:
                    control_deps[node.lineno] = controlling_conditions.copy()
            
            # Process the return value expression if present
            if hasattr(node, 'value') and node.value is not None:
                self._build_control_dependencies(node.value, controlling_conditions, control_deps)
                
        else:
            # Process children with current conditions
            for child in ast.iter_child_nodes(node):
                self._build_control_dependencies(child, controlling_conditions, control_deps)
    
    def _handle_else_elif_chain(self, orelse_nodes: List[ast.AST], all_if_conditions: Set[int], 
                               control_deps: Dict[int, Set[int]]):
        """Handle elif/else chain for control dependencies."""
        for child in orelse_nodes:
            if isinstance(child, ast.If):  # elif
                elif_line = child.lineno
                elif_conditions = all_if_conditions | {elif_line}
                
                for stmt in child.body:
                    self._build_control_dependencies(stmt, elif_conditions, control_deps)
                
                next_conditions = all_if_conditions | {elif_line}
                self._handle_else_elif_chain(child.orelse, next_conditions, control_deps)
            else:  # else body
                self._build_control_dependencies(child, all_if_conditions, control_deps)
    
    def _build_data_dependencies(self, node: ast.AST, var_defs: Dict[str, int], 
                                var_uses: Dict[str, List[int]], pdg: Dict):
        """Build data dependencies, def-use relations, and info-flow relations."""
        if isinstance(node, ast.Assign):
            # Handle variable definitions
            for target in node.targets:
                if isinstance(target, ast.Name):
                    var_name = target.id
                    var_defs[var_name] = node.lineno
                    
                    # Add def-use relations for this variable
                    for use_line in var_uses[var_name]:
                        pdg['def_use'][var_name].add((node.lineno, use_line))
                    var_uses[var_name].clear()  # Clear uses after definition
                    
                    # Build info-flow relations: if this definition uses other variables
                    self._build_info_flow_relations(node, var_name, node.lineno, pdg)
                    
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            # Handle variable uses
            var_name = node.id
            if var_name in var_defs:
                var_uses[var_name].append(node.lineno)
                # Add def-use relation
                pdg['def_use'][var_name].add((var_defs[var_name], node.lineno))
        
        elif isinstance(node, ast.Return):
            # Handle return statements - process the return value expression
            if hasattr(node, 'value') and node.value is not None:
                self._build_data_dependencies(node.value, var_defs, var_uses, pdg)
        
        elif isinstance(node, (ast.Break, ast.Continue)):
            # break and continue statements don't have data dependencies
            # They are purely control flow statements
            pass
        
        # Process children
        for child in ast.iter_child_nodes(node):
            self._build_data_dependencies(child, var_defs, var_uses, pdg)
    
    def _build_info_flow_relations(self, node: ast.AST, target_var: str, def_line: int, pdg: Dict):
        """Build info-flow relations where variable references affect other variable definitions."""
        # Find all variable references in the assignment expression
        for child in ast.walk(node.value) if hasattr(node, 'value') else []:
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                ref_var = child.id
                if ref_var != target_var:  # Don't create self-references
                    # Create info-flow relation: ref_var affects target_var
                    pdg['info_flow'][ref_var].add((child.lineno, def_line))
    
    def _build_sdg(self, tree: ast.AST):
        """
        Build System Dependence Graph (SDG) by linking PDGs through call sites
        and function entries for inter-procedural slicing.
        """
        self.sdg = {
            'call_sites': defaultdict(list),  # function_name -> list of call sites
            'function_entries': {},           # function_name -> entry line
            'parameter_mapping': defaultdict(dict),  # call_site -> {formal: actual}
            'return_mapping': defaultdict(list),     # function_name -> list of return lines
            'assignment_sources': defaultdict(list), # line -> list of (source_line, source_func)
            'variable_assignments': defaultdict(list) # variable -> list of (line, func_name)
        }
        
        # Find all function calls and entries
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Handle function calls
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    if func_name in self.pdgs:
                        self.sdg['call_sites'][func_name].append(node.lineno)
                        
                        # Map actual arguments to formal parameters
                        if func_name in self.pdgs:
                            # This is a simplified mapping - in practice, you'd need
                            # to match actual args with formal parameters
                            self.sdg['parameter_mapping'][node.lineno] = {}
                            
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Record function entry
                self.sdg['function_entries'][node.name] = node.lineno
                
            elif isinstance(node, ast.Return):
                # Find which function this return belongs to
                for func_name, pdg in self.pdgs.items():
                    if node.lineno in pdg['statements']:
                        self.sdg['return_mapping'][func_name].append(node.lineno)
                        break
                        
            elif isinstance(node, ast.Assign):
                # Track variable assignments for inter-procedural analysis
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_name = target.id
                        # Find which function this assignment belongs to
                        for func_name, pdg in self.pdgs.items():
                            if node.lineno in pdg['statements']:
                                self.sdg['variable_assignments'][var_name].append((node.lineno, func_name))
                                break
    
    def _mark_executed_elements(self, executed_lines: Set[int]):
        """
        Mark executed statements and dependencies in the SDG.
        This simulates the execution tracking phase.
        """
        self.executed_statements = executed_lines.copy()
        
        # Mark executed dependencies based on executed statements
        for func_name, pdg in self.pdgs.items():
            for line in executed_lines:
                if line in pdg['statements']:
                    # Mark control dependencies
                    if line in pdg['control_deps']:
                        for dep_line in pdg['control_deps'][line]:
                            if dep_line in executed_lines:
                                self.executed_dependencies.add((dep_line, line))
                    
                    # Mark data dependencies through def-use relations
                    for var, def_use_pairs in pdg['def_use'].items():
                        for def_line, use_line in def_use_pairs:
                            if def_line in executed_lines and use_line in executed_lines:
                                self.executed_dependencies.add((def_line, use_line))
                    
                    # Mark info-flow relations
                    for var, info_flow_pairs in pdg['info_flow'].items():
                        for ref_line, def_line in info_flow_pairs:
                            if ref_line in executed_lines and def_line in executed_lines:
                                self.executed_dependencies.add((ref_line, def_line))
    
    def _compute_dynamic_slice(self, target_line: int):
        """
        Phase 2: Compute dynamic slice by traversing backward along marked
        nodes and edges only.
        """
        self.slice_nodes = set()
        visited = set()
        
        # Start from target line
        to_visit = [target_line]
        
        while to_visit:
            current_line = to_visit.pop()
            if current_line in visited:
                continue
                
            visited.add(current_line)
            
            # Only add to slice if it's not the target line itself
            if current_line != target_line:
                self.slice_nodes.add(current_line)
            
            # Find which function contains this line
            current_func = None
            for func_name, pdg in self.pdgs.items():
                if current_line in pdg['statements']:
                    current_func = func_name
                    break
            
            if current_func is None:
                continue
                
            pdg = self.pdgs[current_func]
            
            # Follow control dependencies (only marked ones)
            if current_line in pdg['control_deps']:
                for dep_line in pdg['control_deps'][current_line]:
                    if (dep_line, current_line) in self.executed_dependencies:
                        to_visit.append(dep_line)
            
            # For conditional line detection, skip data dependencies
            # Only follow control dependencies
            # for var, def_use_pairs in pdg['def_use'].items():
            #     for def_line, use_line in def_use_pairs:
            #         if use_line == current_line and (def_line, use_line) in self.executed_dependencies:
            #             to_visit.append(def_line)
            
            # For conditional line detection, skip info-flow relations
            # Only follow control dependencies
            # for var, info_flow_pairs in pdg['info_flow'].items():
            #     for ref_line, def_line in info_flow_pairs:
            #         if def_line == current_line and (ref_line, def_line) in self.executed_dependencies:
            #             to_visit.append(ref_line)
            
            # Follow inter-procedural dependencies
            self._follow_inter_procedural_deps(current_line, to_visit)
    
    def _follow_inter_procedural_deps(self, current_line: int, to_visit: List[int]):
        """Follow inter-procedural dependencies through function calls and returns."""
        # For conditional line detection, we should be more conservative
        # Only follow control dependencies, not data flow dependencies
        
        # Find function calls at this line
        for func_name, call_sites in self.sdg['call_sites'].items():
            if current_line in call_sites:
                # Only follow into called function if it's a control dependency
                # For conditional line detection, we don't need to follow data flow
                pass
        
        # Skip data flow dependencies for conditional line detection
        # self._follow_data_flow_dependencies(current_line, to_visit)
    
    def _follow_data_flow_dependencies(self, current_line: int, to_visit: List[int]):
        """Follow data flow dependencies through function calls and assignments."""
        # Find which function contains the current line
        current_func = None
        for func_name, pdg in self.pdgs.items():
            if current_line in pdg['statements']:
                current_func = func_name
                break
        
        if current_func is None:
            return
        
        # Check if any variable at current_line comes from a function call
        # This is a simplified analysis - in practice, you'd need more sophisticated tracking
        for var_name, assignments in self.sdg['variable_assignments'].items():
            for assign_line, assign_func in assignments:
                # If this variable is assigned from a function call near the current line
                if assign_func != current_func and abs(assign_line - current_line) <= 3:
                    # Check if there's a function call that could be the source
                    for call_func, call_sites in self.sdg['call_sites'].items():
                        for call_line in call_sites:
                            if abs(call_line - assign_line) <= 2:
                                # Follow into the called function
                                entry_line = self.sdg['function_entries'].get(call_func)
                                if entry_line and entry_line in self.executed_statements:
                                    to_visit.append(entry_line)
                                
                                # Also follow return statements from that function
                                for return_line in self.sdg['return_mapping'].get(call_func, []):
                                    if return_line in self.executed_statements:
                                        to_visit.append(return_line)
    
    # Legacy method for backward compatibility - now uses dynamic slicing
    def find_conditional_lines(self, code: str, target_line: int) -> List[int]:
        """
        Legacy method that now uses dynamic slicing algorithm.
        For backward compatibility with existing code.
        """
        return self.compute_dynamic_slice(code, target_line)


def get_conditional_lines(code: str, target_line: int) -> List[int]:
    """
    Main function to find conditional lines affecting a target line.
    Now uses dynamic slicing algorithm.
    
    Args:
        code: Python source code as string
        target_line: Line number to analyze (1-based)
        
    Returns:
        List of line numbers that conditionally control the target line
    """
    slicer = DynamicSlicer()
    return slicer.find_conditional_lines(code, target_line)


def compute_dynamic_slice(code: str, target_line: int, executed_lines: Set[int] = None) -> List[int]:
    """
    Compute dynamic backward slice using Agrawal and Horgan's algorithm.
    
    This is the main function that implements the two-phase dynamic slicing algorithm:
    Phase 1: Build PDGs and SDG, mark executed statements and dependencies
    Phase 2: Traverse backward along marked nodes and edges only
    
    Args:
        code: Python source code as string
        target_line: Line number to analyze (1-based)
        executed_lines: Set of line numbers that were executed (if None, assumes all lines)
        
    Returns:
        List of line numbers in the dynamic backward slice
    """
    slicer = DynamicSlicer()
    return slicer.compute_dynamic_slice(code, target_line, executed_lines)


def debug_dependencies(code: str) -> Dict[int, Set[int]]:
    """Debug function to see all dependencies using dynamic slicing."""
    slicer = DynamicSlicer()
    tree = ast.parse(code)
    slicer._build_pdgs_and_sdg(tree)
    
    # Return a simplified view of control dependencies
    all_deps = {}
    for func_name, pdg in slicer.pdgs.items():
        for line, deps in pdg['control_deps'].items():
            all_deps[line] = deps
    return all_deps


# Example usage and test cases for all control-flow constructs in Python: if, while, for, try-catch, with, try-except, finally, match-case, break, continue, and return
if __name__ == "__main__":
    # Test case 1: Basic if-else with dynamic slicing
    test_code1 = """if A:     # line 1
    if B:   # line 2
        statement_C  # line 3
    else:   # line 4
        statement_D  # line 5
"""
    
    print("Test case 1 - Dynamic Slicing:")
    print("All dependencies:", debug_dependencies(test_code1))
    
    # Test with different execution scenarios
    print(f"Line 3 depends on (all executed): {get_conditional_lines(test_code1, 3)}")
    print(f"Line 3 depends on (only A=True, B=True): {compute_dynamic_slice(test_code1, 3, {1, 2, 3})}")
    print(f"Line 5 depends on (all executed): {get_conditional_lines(test_code1, 5)}")
    print(f"Line 5 depends on (only A=True, B=False): {compute_dynamic_slice(test_code1, 5, {1, 2, 4, 5})}")
    
    # Test case 2: Complex nested structure
    test_code2 = """if condition1:      # line 1
    while condition2:  # line 2
        if condition3:   # line 3
            statement1    # line 4
        for i in range(10):  # line 5
            statement2    # line 6
            if condition4:  # line 7
                statement3  # line 8
                statement5  # line 9
    else:              # line 10
        statement4      # line 11
"""
    
    print("\nTest case 2:")
    print("All dependencies:", debug_dependencies(test_code2))
    print(f"Line 4 depends on: {get_conditional_lines(test_code2, 4)}")   # [1, 2, 3]
    print(f"Line 6 depends on: {get_conditional_lines(test_code2, 6)}")   # [1, 2, 5]
    print(f"Line 8 depends on: {get_conditional_lines(test_code2, 8)}")   # [1, 2, 5, 7]
    print(f"Line 9 depends on: {get_conditional_lines(test_code2, 9)}") # [1]
    
    # Test case 3: Try-except
    test_code3 = """try:                # line 1
    statement1      # line 2
    if condition:   # line 3
        statement2  # line 4
except Exception1:   # line 5
    statement3      # line 6
except Exception2:   # line 7
    statement4      # line 8
except Exception3:   # line 9
    statement5      # line 10
finally:           # line 11
    statement6      # line 12
"""
    
    print("\nTest case 3:")
    print("All dependencies:", debug_dependencies(test_code3))
    print(f"Line 2 depends on: {get_conditional_lines(test_code3, 2)}")  # [1]
    print(f"Line 4 depends on: {get_conditional_lines(test_code3, 4)}")  # [1, 3]
    print(f"Line 6 depends on: {get_conditional_lines(test_code3, 6)}")  # [5]
    print(f"Line 8 depends on: {get_conditional_lines(test_code3, 8)}")  # [5]
    print(f"Line 12 depends on: {get_conditional_lines(test_code3, 12)}")  # [5]

    # Test case 4: Complex nested if-else
    test_code4 = """if A:           # line 1
    if B:       # line 2
        if C:   # line 3
            stmt1  # line 4
        else:   # line 5
            stmt2  # line 6
    else:       # line 7
        stmt3   # line 8
else:           # line 9
    stmt4       # line 10
"""
    
    print("\nTest case 4 - Nested if-else:")
    print("All dependencies:", debug_dependencies(test_code4))
    print(f"Line 3 depends on: {get_conditional_lines(test_code4, 3)}")   # [1, 2, 3]
    print(f"Line 5 depends on: {get_conditional_lines(test_code4, 5)}")   # [1, 2, 3]
    print(f"Line 8 depends on: {get_conditional_lines(test_code4, 8)}")   # [1, 2]
    print(f"Line 10 depends on: {get_conditional_lines(test_code4, 10)}") # [1]
    
    # Test case 5: if-elif-else chain
    test_code5 = """if A:           # line 1
    stmt1       # line 2
elif B:         # line 3
    stmt2       # line 4
elif C:         # line 5
    stmt3       # line 6
else:           # line 7
    stmt4       # line 8
"""
    
    print("\nTest case 5 - if-elif-else chain:")
    print("All dependencies:", debug_dependencies(test_code5))
    print(f"Line 2 depends on: {get_conditional_lines(test_code5, 2)}")   # [1]
    print(f"Line 4 depends on: {get_conditional_lines(test_code5, 4)}")   # [1, 3]
    print(f"Line 6 depends on: {get_conditional_lines(test_code5, 6)}")   # [1, 3, 5]
    print(f"Line 8 depends on: {get_conditional_lines(test_code5, 8)}")   # [1, 3, 5]

    #Test case 6: Match-case
    test_code6 = """match x:
    case 1:
        print("One")
    case 2:
        print("Two")
    case _:
        print("Other")
"""
    print("\nTest case 6 - Match-case:")
    print("All dependencies:", debug_dependencies(test_code6))
    
    # Test case 7: Break, continue, and return statements
    test_code7 = """def process_data(items):    # line 1
    result = []              # line 2
    for item in items:       # line 3
        if item < 0:         # line 4
            continue         # line 5
        if item > 100:       # line 6
            break            # line 7
        result.append(item)  # line 8
    return result            # line 9
"""
    
    print("\nTest case 7 - Break, Continue, Return:")
    print("All dependencies:", debug_dependencies(test_code7))
    print(f"Line 5 (continue) depends on: {get_conditional_lines(test_code7, 5)}")
    print(f"Line 7 (break) depends on: {get_conditional_lines(test_code7, 7)}")
