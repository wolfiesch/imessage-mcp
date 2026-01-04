// C++ version of the iMessage MCP gateway CLI.
//
// This CLI embeds the existing Python implementation so we can compare
// startup and command execution overhead against the pure-Python gateway.
// It mirrors the Python commands while delegating the heavy lifting to the
// existing MessagesInterface and ContactsManager classes.

#include <Python.h>

#include <filesystem>
#include <iostream>
#include <optional>
#include <sstream>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace fs = std::filesystem;

struct Contact {
    std::string name;
    std::string phone;
    std::string relationship;
    std::string notes;
};

class PyObjectPtr {
public:
    PyObjectPtr() : ptr_(nullptr) {}
    explicit PyObjectPtr(PyObject* obj) : ptr_(obj) {}
    ~PyObjectPtr() { Py_XDECREF(ptr_); }

    PyObject* get() const { return ptr_; }
    PyObject* release() {
        PyObject* tmp = ptr_;
        ptr_ = nullptr;
        return tmp;
    }

    PyObject* operator->() const { return ptr_; }
    explicit operator bool() const { return ptr_ != nullptr; }

private:
    PyObject* ptr_;
};

class PythonGateway {
public:
    PythonGateway() = default;
    ~PythonGateway() {
        if (initialized_) {
            Py_Finalize();
        }
    }

    bool initialize(const fs::path& repo_root, const fs::path& contacts_path) {
        repo_root_ = repo_root;
        contacts_path_ = contacts_path;

        if (initialized_) {
            return true;
        }

        Py_Initialize();

        // Ensure the repository root is on sys.path
        PyObject* sys_path = PySys_GetObject("path");
        PyObjectPtr repo_path(PyUnicode_FromString(repo_root.string().c_str()));
        if (!repo_path) {
            PyErr_Print();
            return false;
        }
        PyList_Insert(sys_path, 0, repo_path.get());

        // Import required modules
        PyObjectPtr messages_module(PyImport_ImportModule("src.messages_interface"));
        PyObjectPtr contacts_module(PyImport_ImportModule("src.contacts_manager"));
        PyObjectPtr json_module(PyImport_ImportModule("json"));

        if (!messages_module || !contacts_module || !json_module) {
            PyErr_Print();
            return false;
        }

        PyObjectPtr messages_class(PyObject_GetAttrString(messages_module.get(), "MessagesInterface"));
        PyObjectPtr contacts_class(PyObject_GetAttrString(contacts_module.get(), "ContactsManager"));
        PyObjectPtr json_dumps(PyObject_GetAttrString(json_module.get(), "dumps"));

        if (!messages_class || !contacts_class || !json_dumps) {
            PyErr_Print();
            return false;
        }

        json_dumps_ = json_dumps.release();

        messages_interface_ = PyObject_CallObject(messages_class.get(), nullptr);
        if (!messages_interface_) {
            PyErr_Print();
            return false;
        }

        PyObjectPtr contacts_path_obj(PyUnicode_FromString(contacts_path.string().c_str()));
        PyObjectPtr contacts_args(PyTuple_Pack(1, contacts_path_obj.get()));
        contacts_manager_ = PyObject_CallObject(contacts_class.get(), contacts_args.get());
        if (!contacts_manager_) {
            PyErr_Print();
            return false;
        }

        initialized_ = true;
        return true;
    }

    std::vector<Contact> list_contacts() {
        std::vector<Contact> contacts;
        PyObjectPtr contact_list(PyObject_CallMethod(contacts_manager_, "list_contacts", nullptr));
        if (!contact_list || !PyList_Check(contact_list.get())) {
            PyErr_Print();
            return contacts;
        }

        const Py_ssize_t size = PyList_Size(contact_list.get());
        contacts.reserve(static_cast<size_t>(size));
        for (Py_ssize_t i = 0; i < size; ++i) {
            PyObject* item = PyList_GetItem(contact_list.get(), i);  // Borrowed ref
            auto contact = contact_from_py(item);
            if (contact) {
                contacts.push_back(*contact);
            }
        }
        return contacts;
    }

    std::optional<Contact> resolve_contact(const std::string& name) {
        PyObjectPtr contact_obj(PyObject_CallMethod(contacts_manager_, "get_contact_by_name", "(s)", name.c_str()));
        if (!contact_obj) {
            PyErr_Print();
            return std::nullopt;
        }

        if (contact_obj.get() == Py_None) {
            return std::nullopt;
        }
        return contact_from_py(contact_obj.get());
    }

    PyObjectPtr send_message(const std::string& phone, const std::string& message) {
        return PyObjectPtr(PyObject_CallMethod(messages_interface_, "send_message", "(ss)", phone.c_str(), message.c_str()));
    }

    PyObjectPtr messages_by_phone(const std::string& phone, int limit) {
        return PyObjectPtr(PyObject_CallMethod(messages_interface_, "get_messages_by_phone", "(si)", phone.c_str(), limit));
    }

    PyObjectPtr search_messages(const std::string& query, const std::optional<std::string>& phone, int limit) {
        PyObject* phone_obj = optional_string(phone);
        PyObjectPtr result(PyObject_CallMethod(messages_interface_, "search_messages", "(sOi)", query.c_str(), phone_obj, limit));
        Py_DECREF(phone_obj);
        return result;
    }

    PyObjectPtr all_recent(int limit) {
        return PyObjectPtr(PyObject_CallMethod(messages_interface_, "get_all_recent_conversations", "(i)", limit));
    }

    PyObjectPtr unread(int limit) {
        return PyObjectPtr(PyObject_CallMethod(messages_interface_, "get_unread_messages", "(i)", limit));
    }

    PyObjectPtr analytics(const std::optional<std::string>& phone, int days) {
        PyObject* phone_obj = optional_string(phone);
        PyObjectPtr result(PyObject_CallMethod(messages_interface_, "get_conversation_analytics", "(Oi)", phone_obj, days));
        Py_DECREF(phone_obj);
        return result;
    }

    PyObjectPtr followups(int days, int stale_days) {
        return PyObjectPtr(PyObject_CallMethod(messages_interface_, "detect_follow_up_needed", "(ii)", days, stale_days));
    }

    PyObjectPtr list_groups(int limit) {
        return PyObjectPtr(PyObject_CallMethod(messages_interface_, "list_group_chats", "(i)", limit));
    }

    PyObjectPtr group_messages(const std::optional<std::string>& group_id,
                               const std::optional<std::string>& participant,
                               int limit) {
        PyObject* group_obj = optional_string(group_id);
        PyObject* participant_obj = optional_string(participant);
        PyObjectPtr result(PyObject_CallMethod(messages_interface_, "get_group_messages",
                                               "(OOi)", group_obj, participant_obj, limit));
        Py_DECREF(group_obj);
        Py_DECREF(participant_obj);
        return result;
    }

    PyObjectPtr attachments(const std::optional<std::string>& phone,
                            const std::optional<std::string>& mime_type,
                            int limit) {
        PyObject* phone_obj = optional_string(phone);
        PyObject* mime_obj = optional_string(mime_type);
        PyObjectPtr result(PyObject_CallMethod(messages_interface_, "get_attachments",
                                               "(OOi)", phone_obj, mime_obj, limit));
        Py_DECREF(phone_obj);
        Py_DECREF(mime_obj);
        return result;
    }

    PyObjectPtr add_contact(const Contact& contact) {
        return PyObjectPtr(PyObject_CallMethod(
            contacts_manager_,
            "add_contact",
            "(ssss)",
            contact.name.c_str(),
            contact.phone.c_str(),
            contact.relationship.c_str(),
            contact.notes.c_str()));
    }

    PyObjectPtr reactions(const std::optional<std::string>& phone, int limit) {
        PyObject* phone_obj = optional_string(phone);
        PyObjectPtr result(PyObject_CallMethod(messages_interface_, "get_reactions", "(Oi)", phone_obj, limit));
        Py_DECREF(phone_obj);
        return result;
    }

    PyObjectPtr links(const std::optional<std::string>& phone,
                      const std::optional<int>& days,
                      int limit) {
        PyObject* phone_obj = optional_string(phone);
        PyObject* days_obj = days ? PyLong_FromLong(*days) : Py_None;
        Py_INCREF(days_obj);
        PyObjectPtr result(PyObject_CallMethod(messages_interface_, "extract_links", "(OOi)", phone_obj, days_obj, limit));
        Py_DECREF(phone_obj);
        Py_DECREF(days_obj);
        return result;
    }

    PyObjectPtr voice(const std::optional<std::string>& phone, int limit) {
        PyObject* phone_obj = optional_string(phone);
        PyObjectPtr result(PyObject_CallMethod(messages_interface_, "get_voice_messages", "(Oi)", phone_obj, limit));
        Py_DECREF(phone_obj);
        return result;
    }

    PyObjectPtr message_thread(const std::string& guid, int limit) {
        return PyObjectPtr(PyObject_CallMethod(messages_interface_, "get_message_thread", "(si)", guid.c_str(), limit));
    }

    PyObjectPtr handles(int days, int limit) {
        return PyObjectPtr(PyObject_CallMethod(messages_interface_, "list_recent_handles", "(ii)", days, limit));
    }

    PyObjectPtr unknown_senders(const std::vector<Contact>& contacts, int days, int limit) {
        PyObjectPtr known(PyList_New(static_cast<Py_ssize_t>(contacts.size())));
        for (size_t i = 0; i < contacts.size(); ++i) {
            PyList_SetItem(known.get(), static_cast<Py_ssize_t>(i), PyUnicode_FromString(contacts[i].phone.c_str()));
        }
        PyObjectPtr result(PyObject_CallMethod(messages_interface_, "search_unknown_senders", "(Oii)", known.get(), days, limit));
        return result;
    }

    PyObjectPtr scheduled() {
        return PyObjectPtr(PyObject_CallMethod(messages_interface_, "get_scheduled_messages", nullptr));
    }

    PyObjectPtr summary(const std::string& phone, const std::optional<int>& days, int limit) {
        PyObject* days_obj = days ? PyLong_FromLong(*days) : Py_None;
        Py_INCREF(days_obj);
        PyObjectPtr phone_obj(PyUnicode_FromString(phone.c_str()));
        PyObjectPtr result(PyObject_CallMethod(messages_interface_, "get_conversation_for_summary",
                                               "(OOi)", phone_obj.get(), days_obj, limit));
        Py_DECREF(days_obj);
        return result;
    }

    std::string to_json(PyObject* obj, bool pretty = true) {
        if (!obj || !json_dumps_) {
            return "{}";
        }

        PyObjectPtr args(PyTuple_Pack(1, obj));
        PyObjectPtr kwargs(PyDict_New());
        PyDict_SetItemString(kwargs.get(), "ensure_ascii", Py_False);
        if (pretty) {
            PyObjectPtr indent(PyLong_FromLong(2));
            PyDict_SetItemString(kwargs.get(), "indent", indent.get());
        }

        PyObjectPtr json_str(PyObject_Call(json_dumps_, args.get(), kwargs.get()));
        if (!json_str) {
            PyErr_Print();
            return "{}";
        }

        return PyUnicode_AsUTF8(json_str.get());
    }

private:
    PyObject* optional_string(const std::optional<std::string>& value) {
        if (value) {
            return PyUnicode_FromString(value->c_str());
        }
        Py_INCREF(Py_None);
        return Py_None;
    }

    std::optional<Contact> contact_from_py(PyObject* obj) {
        if (!obj || obj == Py_None) {
            return std::nullopt;
        }
        Contact contact;
        PyObjectPtr name(PyObject_GetAttrString(obj, "name"));
        PyObjectPtr phone(PyObject_GetAttrString(obj, "phone"));
        PyObjectPtr relationship(PyObject_GetAttrString(obj, "relationship_type"));
        PyObjectPtr notes(PyObject_GetAttrString(obj, "notes"));

        if (!name || !phone) {
            return std::nullopt;
        }

        contact.name = PyUnicode_AsUTF8(name.get());
        contact.phone = PyUnicode_AsUTF8(phone.get());
        contact.relationship = relationship ? PyUnicode_AsUTF8(relationship.get()) : "";
        contact.notes = notes ? PyUnicode_AsUTF8(notes.get()) : "";
        return contact;
    }

    PyObject* messages_interface_{nullptr};
    PyObject* contacts_manager_{nullptr};
    PyObject* json_dumps_{nullptr};
    bool initialized_{false};
    fs::path repo_root_;
    fs::path contacts_path_;
};

struct ParsedArgs {
    std::string command;
    std::vector<std::string> positional;
    std::unordered_map<std::string, std::string> options;
    bool json{false};
};

ParsedArgs parse_args(int argc, char** argv) {
    ParsedArgs parsed;
    if (argc > 1) {
        parsed.command = argv[1];
    }

    for (int i = 2; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--json") {
            parsed.json = true;
            continue;
        }
        if (arg.rfind("--", 0) == 0 || arg.rfind("-", 0) == 0) {
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                parsed.options[arg] = argv[++i];
            } else {
                parsed.options[arg] = "";
            }
        } else {
            parsed.positional.emplace_back(arg);
        }
    }
    return parsed;
}

int usage(int exit_code = 1) {
    std::cout << "iMessage Gateway (C++) - commands:\n"
              << "  search <contact> [--query <text>] [--limit N] [--json]\n"
              << "  messages <contact> [--limit N] [--json]\n"
              << "  recent [--limit N] [--json]\n"
              << "  unread [--limit N] [--json]\n"
              << "  send <contact> <message...>\n"
              << "  contacts [--json]\n"
              << "  analytics [contact] [--days N] [--json]\n"
              << "  followup [--days N] [--stale N] [--json]\n"
              << "  groups [--limit N] [--json]\n"
              << "  group-messages [--group-id ID] [--participant PHONE] [--limit N] [--json]\n"
              << "  attachments [contact] [--type MIME] [--limit N] [--json]\n"
              << "  reactions [contact] [--limit N] [--json]\n"
              << "  links [contact] [--days N] [--limit N] [--json]\n"
              << "  voice [contact] [--limit N] [--json]\n"
              << "  thread --guid GUID [--limit N] [--json]\n"
              << "  handles [--days N] [--limit N] [--json]\n"
              << "  unknown [--days N] [--limit N] [--json]\n"
              << "  scheduled [--json]\n"
              << "  summary <contact> [--days N] [--limit N] [--json]\n"
              << "  add-contact <name> <phone> [--relationship type] [--notes text]\n";
    return exit_code;
}

int main(int argc, char** argv) {
    const fs::path repo_root = fs::absolute(fs::path(argv[0])).parent_path().parent_path().parent_path();
    const fs::path contacts_path = repo_root / "config" / "contacts.json";

    ParsedArgs args = parse_args(argc, argv);
    if (args.command.empty()) {
        return usage();
    }

    if (args.command == "--help" || args.command == "-h") {
        return usage(0);
    }

    PythonGateway gateway;
    if (!gateway.initialize(repo_root, contacts_path)) {
        std::cerr << "Failed to initialize Python environment.\n";
        return 1;
    }

    auto to_int = [](const std::unordered_map<std::string, std::string>& opts,
                     const std::string& key,
                     int default_val) {
        auto it = opts.find(key);
        if (it != opts.end()) {
            try {
                return std::stoi(it->second);
            } catch (...) {
                return default_val;
            }
        }
        return default_val;
    };

    auto optional_int = [](const std::unordered_map<std::string, std::string>& opts,
                           const std::string& primary,
                           const std::string& secondary) -> std::optional<int> {
        auto it = opts.find(primary);
        if (it == opts.end()) {
            it = opts.find(secondary);
        }
        if (it != opts.end()) {
            try {
                return std::stoi(it->second);
            } catch (...) {
                return std::nullopt;
            }
        }
        return std::nullopt;
    };

    const int limit_default = 20;

    if (args.command == "contacts") {
        auto contacts = gateway.list_contacts();
        if (args.json) {
            std::stringstream ss;
            ss << "[";
            for (size_t i = 0; i < contacts.size(); ++i) {
                if (i > 0) ss << ",";
                ss << "{\"name\":\"" << contacts[i].name << "\","
                   << "\"phone\":\"" << contacts[i].phone << "\","
                   << "\"relationship_type\":\"" << contacts[i].relationship << "\","
                   << "\"notes\":\"" << contacts[i].notes << "\"}";
            }
            ss << "]";
            std::cout << ss.str() << "\n";
        } else {
            std::cout << "Contacts (" << contacts.size() << "):\n";
            for (const auto& c : contacts) {
                std::cout << " - " << c.name << ": " << c.phone << "\n";
            }
        }
        return 0;
    }

    if (args.command == "send") {
        if (args.positional.size() < 2) {
            std::cerr << "Usage: send <contact> <message>\n";
            return 1;
        }
        const auto contact_name = args.positional.front();
        std::string message;
        for (size_t i = 1; i < args.positional.size(); ++i) {
            if (i > 1) message += " ";
            message += args.positional[i];
        }
        auto contact = gateway.resolve_contact(contact_name);
        if (!contact) {
            std::cerr << "Contact not found: " << contact_name << "\n";
            return 1;
        }
        PyObjectPtr result = gateway.send_message(contact->phone, message);
        std::cout << gateway.to_json(result.get()) << "\n";
        return 0;
    }

    if (args.command == "messages") {
        if (args.positional.empty()) {
            std::cerr << "Usage: messages <contact> [--limit N]\n";
            return 1;
        }
        const auto contact_name = args.positional.front();
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", limit_default));
        auto contact = gateway.resolve_contact(contact_name);
        if (!contact) {
            std::cerr << "Contact not found: " << contact_name << "\n";
            return 1;
        }
        PyObjectPtr result = gateway.messages_by_phone(contact->phone, limit);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "search") {
        if (args.positional.empty()) {
            std::cerr << "Usage: search <contact> [--query text] [--limit N]\n";
            return 1;
        }
        const auto contact_name = args.positional.front();
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", limit_default));
        const auto query_it = args.options.find("--query") != args.options.end()
                                  ? args.options.find("--query")
                                  : args.options.find("-q");
        std::optional<std::string> query;
        if (query_it != args.options.end()) {
            query = query_it->second;
        }
        auto contact = gateway.resolve_contact(contact_name);
        if (!contact) {
            std::cerr << "Contact not found: " << contact_name << "\n";
            return 1;
        }
        PyObjectPtr result;
        if (query) {
            result = gateway.search_messages(*query, contact->phone, limit);
        } else {
            result = gateway.messages_by_phone(contact->phone, limit);
        }
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "recent") {
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", limit_default));
        PyObjectPtr result = gateway.all_recent(limit);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "unread") {
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", limit_default));
        PyObjectPtr result = gateway.unread(limit);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "analytics") {
        std::optional<std::string> phone;
        if (!args.positional.empty()) {
            auto contact = gateway.resolve_contact(args.positional.front());
            if (!contact) {
                std::cerr << "Contact not found: " << args.positional.front() << "\n";
                return 1;
            }
            phone = contact->phone;
        }
        const int days = to_int(args.options, "--days", to_int(args.options, "-d", 30));
        PyObjectPtr result = gateway.analytics(phone, days);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "followup") {
        const int days = to_int(args.options, "--days", to_int(args.options, "-d", 7));
        const int stale = to_int(args.options, "--stale", to_int(args.options, "-s", 2));
        PyObjectPtr result = gateway.followups(days, stale);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "groups") {
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", 50));
        PyObjectPtr result = gateway.list_groups(limit);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "group-messages") {
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", 50));
        std::optional<std::string> group_id;
        std::optional<std::string> participant;
        if (auto it = args.options.find("--group-id"); it != args.options.end()) {
            group_id = it->second;
        } else if (auto it_short = args.options.find("-g"); it_short != args.options.end()) {
            group_id = it_short->second;
        }
        if (auto it = args.options.find("--participant"); it != args.options.end()) {
            participant = it->second;
        } else if (auto it_short = args.options.find("-p"); it_short != args.options.end()) {
            participant = it_short->second;
        }

        if (!group_id && !participant) {
            std::cerr << "Provide --group-id or --participant\n";
            return 1;
        }
        PyObjectPtr result = gateway.group_messages(group_id, participant, limit);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "attachments") {
        std::optional<std::string> phone;
        if (!args.positional.empty()) {
            auto contact = gateway.resolve_contact(args.positional.front());
            if (!contact) {
                std::cerr << "Contact not found: " << args.positional.front() << "\n";
                return 1;
            }
            phone = contact->phone;
        }
        std::optional<std::string> type_filter;
        if (auto it = args.options.find("--type"); it != args.options.end()) {
            type_filter = it->second;
        } else if (auto it_short = args.options.find("-t"); it_short != args.options.end()) {
            type_filter = it_short->second;
        }
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", 50));
        PyObjectPtr result = gateway.attachments(phone, type_filter, limit);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "add-contact") {
        if (args.positional.size() < 2) {
            std::cerr << "Usage: add-contact <name> <phone>\n";
            return 1;
        }
        Contact contact;
        contact.name = args.positional[0];
        contact.phone = args.positional[1];
        auto relationship = args.options.find("--relationship");
        if (relationship == args.options.end()) {
            relationship = args.options.find("-r");
        }
        contact.relationship = relationship != args.options.end() ? relationship->second : "other";
        auto notes = args.options.find("--notes");
        if (notes == args.options.end()) {
            notes = args.options.find("-n");
        }
        contact.notes = notes != args.options.end() ? notes->second : "";
        PyObjectPtr result = gateway.add_contact(contact);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "reactions") {
        std::optional<std::string> phone;
        if (!args.positional.empty()) {
            auto contact = gateway.resolve_contact(args.positional.front());
            if (!contact) {
                std::cerr << "Contact not found: " << args.positional.front() << "\n";
                return 1;
            }
            phone = contact->phone;
        }
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", 100));
        PyObjectPtr result = gateway.reactions(phone, limit);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "links") {
        std::optional<std::string> phone;
        if (!args.positional.empty()) {
            auto contact = gateway.resolve_contact(args.positional.front());
            if (!contact) {
                std::cerr << "Contact not found: " << args.positional.front() << "\n";
                return 1;
            }
            phone = contact->phone;
        }
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", 100));
        std::optional<int> days = optional_int(args.options, "--days", "-d");
        PyObjectPtr result = gateway.links(phone, days, limit);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "voice") {
        std::optional<std::string> phone;
        if (!args.positional.empty()) {
            auto contact = gateway.resolve_contact(args.positional.front());
            if (!contact) {
                std::cerr << "Contact not found: " << args.positional.front() << "\n";
                return 1;
            }
            phone = contact->phone;
        }
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", 50));
        PyObjectPtr result = gateway.voice(phone, limit);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "thread") {
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", 50));
        std::string guid;
        if (auto it = args.options.find("--guid"); it != args.options.end()) {
            guid = it->second;
        } else if (auto it_short = args.options.find("-g"); it_short != args.options.end()) {
            guid = it_short->second;
        }
        if (guid.empty()) {
            std::cerr << "Provide --guid\n";
            return 1;
        }
        PyObjectPtr result = gateway.message_thread(guid, limit);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "handles") {
        const int days = to_int(args.options, "--days", to_int(args.options, "-d", 30));
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", 100));
        PyObjectPtr result = gateway.handles(days, limit);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "unknown") {
        const int days = to_int(args.options, "--days", to_int(args.options, "-d", 30));
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", 100));
        auto contacts = gateway.list_contacts();
        PyObjectPtr result = gateway.unknown_senders(contacts, days, limit);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "scheduled") {
        PyObjectPtr result = gateway.scheduled();
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    if (args.command == "summary") {
        if (args.positional.empty()) {
            std::cerr << "Usage: summary <contact> [--days N] [--limit N]\n";
            return 1;
        }
        auto contact = gateway.resolve_contact(args.positional.front());
        if (!contact) {
            std::cerr << "Contact not found: " << args.positional.front() << "\n";
            return 1;
        }
        const int limit = to_int(args.options, "--limit", to_int(args.options, "-l", 200));
        std::optional<int> days = optional_int(args.options, "--days", "-d");
        PyObjectPtr result = gateway.summary(contact->phone, days, limit);
        std::cout << gateway.to_json(result.get(), args.json) << "\n";
        return 0;
    }

    return usage();
}
