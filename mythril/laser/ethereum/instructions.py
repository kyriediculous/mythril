from mythril.laser.ethereum import util
from ethereum import utils
from z3 import BitVecVal, BitVec, BoolRef, Extract, If, UDiv, URem, simplify, Concat, ULT, UGT, BitVecNumRef, Not, \
    is_false, is_true, ExprRef
from mythril.laser.ethereum.svm import GlobalState
import mythril.laser.ethereum.util as helper
import ethereum.opcodes as opcodes
from z3 import BitVecVal, If, BoolRef
from copy import copy
import logging

TT256M1 = 2 ** 256 - 1

class StackUnderflowException(Exception):
    pass


def instruction(func):
    """ Wrapper that handles copy and original return """
    def wrapper(self, global_state):
        new_global_state = copy(global_state)
        new_global_state.mstate.pc += 1
        return global_state, func(self, new_global_state)
    return wrapper


class Instruction:
    """
    Instruction class is used to mutate a state according to the current instruction
    """
    def __init__(self, op_code):
        assert any(lambda opcodes_element: op_code == opcodes_element[0], opcodes.opcodes)
        self.op_code = op_code

    def evaluate(self, global_state):
        """ Performs the mutation for this instruction """

        # Generalize some ops
        op = self.op_code.lower()
        if self.op_code.startswith("PUSH"):
            op = "push"
        elif self.op_code.startswith("DUP"):
            op = "dup"
        elif self.op_code.startswith("SWAP"):
            op = "swap"
        elif self.op_code.startswith("LOG"):
            op = "log"

        instruction_mutator = getattr(self, op + '_', None)

        if instruction_mutator is None:
            raise NotImplemented()

        return instruction_mutator(global_state)

    @instruction
    def add_(self, global_state):
        mstate = global_state.mstate
        mstate.stack.append((helper.pop_bitvec(mstate) + helper.pop_bitvec(mstate)))
        return [global_state]

    @instruction
    def push_(self, global_state):
        value = BitVecVal(int(global_state.get_current_instruction()['argument'][2:], 16), 256)
        global_state.mstate.stack.append(value)
        return [global_state]

    @instruction
    def dup_(self, global_state):
        value = BitVecVal(int(global_state.get_current_instruction()['argument'][2:], 16), 256)
        global_state.mstate.stack.append(value)
        return [global_state]

    @instruction
    def swap_(self, global_state):
        depth = int(self.op_code[4:])
        try:
            stack = global_state.mstate.stack
            stack[-depth - 1], stack[-1] = stack[-1], stack[-depth - 1]
        except IndexError:
            raise StackUnderflowException()

    @instruction
    def pop_(self, global_state):
        try:
            global_state.mstate.stack.pop()
        except IndexError:
            raise StackUnderflowException()

    @instruction
    def and_(self, global_state):
        try:
            stack = global_state.mstate.stack
            op1, op2 = stack.pop(), stack.pop()
            if type(op1) == BoolRef:
                op1 = If(op1, BitVecVal(1, 256), BitVecVal(0, 256))
            if type(op2) == BoolRef:
                op2 = If(op2, BitVecVal(1, 256), BitVecVal(0, 256))

            stack.append(op1 & op2)
        except IndexError:
            raise StackUnderflowException()

    @instruction
    def or_(self, global_state):
        stack = global_state.mstate.stack
        try:
            op1, op2 = stack.pop(), stack.pop()

            if type(op1) == BoolRef:
                op1 = If(op1, BitVecVal(1, 256), BitVecVal(0, 256))

            if type(op2) == BoolRef:
                op2 = If(op2, BitVecVal(1, 256), BitVecVal(0, 256))

            stack.append(op1 | op2)
        except IndexError:  # Stack underflow
            raise StackUnderflowException()

    @instruction
    def xor_(self, global_state):
        mstate = global_state.mstate
        mstate.stack.append(mstate.stack.pop() ^ mstate.stack.pop())

    @instruction
    def not_(self, global_state: GlobalState):
        mstate = global_state.mstate
        mstate.stack.append(TT256M1 - mstate.stack.pop())


    @instruction
    def byte_(self, global_state):
        mstate = global_state.mstate
        s0, s1 = mstate.stack.pop(), mstate.stack.pop()

        try:
            n = util.get_concrete_int(s0)
            oft = (31 - n) * 8
            result = Concat(BitVecVal(0, 248), Extract(oft + 7, oft, s1))
        except AttributeError:
            logging.debug("BYTE: Unsupported symbolic byte offset")
            result = BitVec(str(simplify(s1)) + "_" + str(simplify(s0)), 256)

        mstate.stack.append(simplify(result))

