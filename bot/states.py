from aiogram.fsm.state import State, StatesGroup


class ExchangeStates(StatesGroup):
    selecting_type = State()
    selecting_from_currency = State()
    selecting_to_currency = State()
    entering_amount = State()
    selecting_network = State()
    selecting_whitelist_address = State()
    entering_address = State()
    confirming_whitelist_submission = State()
    confirming = State()


class SupportStates(StatesGroup):
    waiting_message = State()


class ProfileDocumentStates(StatesGroup):
    selecting_type = State()
    waiting_document = State()
