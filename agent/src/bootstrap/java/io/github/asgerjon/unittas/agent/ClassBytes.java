package io.github.asgerjon.unittas.agent;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * A class file as the agent needs it (SPEC.md 19.7 step 6; the format is JVMS chapter 4): its constant pool read
 * entry by entry, so that entries can be replaced where they are and new ones follow the old; its fields and methods
 * by their access, name, descriptor and attributes; its own attributes; the rest kept as the bytes it was. Written
 * back, every entry keeps its index, so all that names one stays as it was unless the entry itself was replaced. The
 * rewriter (Rewriter, Wrapper) adds methods; the renamer (Renamer) replaces entries. JDK only, on any Java from 17.
 */
final class ClassBytes {

	static final int PUBLIC = 0x0001;
	static final int PRIVATE = 0x0002;
	static final int PROTECTED = 0x0004;
	static final int STATIC = 0x0008;
	static final int NATIVE = 0x0100;
	static final int INTERFACE = 0x0200;
	static final int ABSTRACT = 0x0400;
	static final int SYNTHETIC = 0x1000;

	static final int UTF8 = 1;
	static final int INTEGER = 3;
	static final int FLOAT = 4;
	static final int LONG = 5;
	static final int DOUBLE = 6;
	static final int CLASS = 7;
	static final int STRING = 8;
	static final int FIELD = 9;
	static final int METHOD = 10;
	static final int INTERFACE_METHOD = 11;
	static final int NAME_AND_TYPE = 12;
	static final int METHOD_HANDLE = 15;
	static final int METHOD_TYPE = 16;
	static final int DYNAMIC = 17;
	static final int INVOKE_DYNAMIC = 18;
	static final int MODULE = 19;
	static final int PACKAGE = 20;

	/** A field or a method: what the agent reads and changes of it, its attributes as they were. */
	static final class Member {

		int access;
		int name;
		int descriptor;
		final List<Attribute> attributes;

		Member(int access, int name, int descriptor, List<Attribute> attributes) {
			this.access = access;
			this.name = name;
			this.descriptor = descriptor;
			this.attributes = attributes;
		}
	}

	/** An attribute: its name's entry and its body. */
	record Attribute(int name, byte[] body) {
	}

	private final int minor;
	private final int major;
	/** Each entry's bytes, its tag first, at its index: none at 0 nor after a long or a double (JVMS 4.4.5). */
	private final List<byte[]> pool = new ArrayList<>();
	/** The entries added, by what they are, so each is added once. */
	private final Map<String, Integer> added = new HashMap<>();
	final int access;
	final int thisClass;
	final int superClass;
	/** The interfaces' Class entries. */
	final int[] interfaces;
	final List<Member> fields = new ArrayList<>();
	final List<Member> methods = new ArrayList<>();
	final List<Attribute> attributes = new ArrayList<>();

	ClassBytes(byte[] bytes) throws IOException {
		DataInputStream in = new DataInputStream(new ByteArrayInputStream(bytes));
		if (in.readInt() != 0xCAFEBABE) {
			throw new IllegalArgumentException("not a class file");
		}
		minor = in.readUnsignedShort();
		major = in.readUnsignedShort();
		int count = in.readUnsignedShort();
		pool.add(null);
		for (int index = 1; index < count; index++) {
			int tag = in.readUnsignedByte();
			int size;
			switch (tag) {
				case UTF8:
					size = 2 + peekShort(in);
					break;
				case INTEGER:
				case FLOAT:
				case FIELD:
				case METHOD:
				case INTERFACE_METHOD:
				case NAME_AND_TYPE:
				case DYNAMIC:
				case INVOKE_DYNAMIC:
					size = 4;
					break;
				case LONG:
				case DOUBLE:
					size = 8;
					break;
				case CLASS:
				case STRING:
				case METHOD_TYPE:
				case MODULE:
				case PACKAGE:
					size = 2;
					break;
				case METHOD_HANDLE:
					size = 3;
					break;
				default:
					throw new IllegalArgumentException("an unknown constant pool tag " + tag + " at entry " + index);
			}
			byte[] entry = new byte[1 + size];
			entry[0] = (byte) tag;
			in.readFully(entry, 1, size);
			pool.add(entry);
			if (tag == LONG || tag == DOUBLE) {
				pool.add(null);
				index++;
			}
		}
		access = in.readUnsignedShort();
		thisClass = in.readUnsignedShort();
		superClass = in.readUnsignedShort();
		interfaces = new int[in.readUnsignedShort()];
		for (int i = 0; i < interfaces.length; i++) {
			interfaces[i] = in.readUnsignedShort();
		}
		readMembers(in, fields);
		readMembers(in, methods);
		readAttributes(in, attributes);
		if (in.read() != -1) {
			throw new IllegalArgumentException("bytes after the class file's end");
		}
	}

	/** How many entries the pool has room for (its count: the last index is one less). */
	int poolSize() {
		return pool.size();
	}

	/** An entry's tag, or 0 where there is none (index 0, the slot after a long or a double). */
	int tag(int index) {
		byte[] entry = pool.get(index);
		return entry == null ? 0 : entry[0];
	}

	/** One of an entry's two-byte references (the which-th after its tag: a Class entry's name is its 0th). */
	int reference(int index, int which) {
		byte[] entry = pool.get(index);
		int at = 1 + 2 * which;
		if (entry[0] == METHOD_HANDLE) {
			// its kind (one byte), then its reference
			at = 2;
		}
		return ((entry[at] & 0xFF) << 8) | (entry[at + 1] & 0xFF);
	}

	/** A Utf8 entry's text. */
	String utf8(int index) {
		byte[] entry = entry(index, UTF8);
		try {
			return new DataInputStream(new ByteArrayInputStream(entry, 1, entry.length - 1)).readUTF();
		} catch (IOException e) {
			throw new IllegalArgumentException("entry " + index + " isn't modified UTF-8", e);
		}
	}

	/** A Class entry's name (java/lang/Object, or an array's descriptor). */
	String className(int index) {
		entry(index, CLASS);
		return utf8(reference(index, 0));
	}

	/** The class's own name. */
	String name() {
		return className(thisClass);
	}

	/** The superclass's name, or "" for java/lang/Object's own file. */
	String superName() {
		return superClass == 0 ? "" : className(superClass);
	}

	/** An entry put in place of the one at that index: the same tag and size of slot (never a long or a double). */
	void replace(int index, int tag, int... references) {
		byte[] old = pool.get(index);
		if (old == null || old[0] != tag || tag == LONG || tag == DOUBLE || tag == METHOD_HANDLE) {
			throw new IllegalArgumentException("entry " + index + " can't be replaced by one of tag " + tag);
		}
		pool.set(index, entryOf(tag, references));
	}

	int utf8(String text) {
		ByteArrayOutputStream bytes = new ByteArrayOutputStream();
		try {
			DataOutputStream out = new DataOutputStream(bytes);
			out.writeByte(UTF8);
			out.writeUTF(text);
		} catch (IOException e) {
			throw new IllegalStateException(e);
		}
		return add("utf8 " + text, bytes.toByteArray());
	}

	int classRef(String internalName) {
		return add("class " + internalName, entryOf(CLASS, utf8(internalName)));
	}

	int string(String text) {
		return add("string " + text, entryOf(STRING, utf8(text)));
	}

	int methodRef(String owner, String name, String descriptor) {
		return add("method " + owner + "." + name + descriptor,
			entryOf(METHOD, classRef(owner), nameAndType(name, descriptor)));
	}

	int interfaceMethodRef(String owner, String name, String descriptor) {
		return add("interface method " + owner + "." + name + descriptor,
			entryOf(INTERFACE_METHOD, classRef(owner), nameAndType(name, descriptor)));
	}

	int nameAndType(String name, String descriptor) {
		return add("name and type " + name + descriptor, entryOf(NAME_AND_TYPE, utf8(name), utf8(descriptor)));
	}

	/** The class file again, the new entries after the old ones. */
	byte[] bytes() {
		ByteArrayOutputStream bytes = new ByteArrayOutputStream();
		try {
			DataOutputStream out = new DataOutputStream(bytes);
			out.writeInt(0xCAFEBABE);
			out.writeShort(minor);
			out.writeShort(major);
			out.writeShort(pool.size());
			for (byte[] entry : pool) {
				if (entry != null) {
					out.write(entry);
				}
			}
			out.writeShort(access);
			out.writeShort(thisClass);
			out.writeShort(superClass);
			out.writeShort(interfaces.length);
			for (int each : interfaces) {
				out.writeShort(each);
			}
			writeMembers(out, fields);
			writeMembers(out, methods);
			writeAttributes(out, attributes);
		} catch (IOException e) {
			throw new IllegalStateException(e);
		}
		return bytes.toByteArray();
	}

	private byte[] entry(int index, int tag) {
		byte[] entry = index > 0 && index < pool.size() ? pool.get(index) : null;
		if (entry == null || entry[0] != tag) {
			throw new IllegalArgumentException("entry " + index + " isn't of tag " + tag);
		}
		return entry;
	}

	private static byte[] entryOf(int tag, int... references) {
		byte[] entry = new byte[1 + 2 * references.length];
		entry[0] = (byte) tag;
		for (int i = 0; i < references.length; i++) {
			entry[1 + 2 * i] = (byte) (references[i] >> 8);
			entry[2 + 2 * i] = (byte) references[i];
		}
		return entry;
	}

	private int add(String key, byte[] entry) {
		Integer known = added.get(key);
		if (known != null) {
			return known;
		}
		if (pool.size() >= 0xFFFF) {
			throw new IllegalArgumentException("the constant pool is full");
		}
		pool.add(entry);
		added.put(key, pool.size() - 1);
		return pool.size() - 1;
	}

	private static int peekShort(DataInputStream in) throws IOException {
		in.mark(2);
		int value = in.readUnsignedShort();
		in.reset();
		return value;
	}

	private static void readMembers(DataInputStream in, List<Member> into) throws IOException {
		int count = in.readUnsignedShort();
		for (int i = 0; i < count; i++) {
			int flags = in.readUnsignedShort();
			int name = in.readUnsignedShort();
			int descriptor = in.readUnsignedShort();
			List<Attribute> its = new ArrayList<>();
			readAttributes(in, its);
			into.add(new Member(flags, name, descriptor, its));
		}
	}

	private static void readAttributes(DataInputStream in, List<Attribute> into) throws IOException {
		int count = in.readUnsignedShort();
		for (int i = 0; i < count; i++) {
			int name = in.readUnsignedShort();
			byte[] body = new byte[in.readInt()];
			in.readFully(body);
			into.add(new Attribute(name, body));
		}
	}

	private static void writeMembers(DataOutputStream out, List<Member> members) throws IOException {
		out.writeShort(members.size());
		for (Member member : members) {
			out.writeShort(member.access);
			out.writeShort(member.name);
			out.writeShort(member.descriptor);
			writeAttributes(out, member.attributes);
		}
	}

	private static void writeAttributes(DataOutputStream out, List<Attribute> attributes) throws IOException {
		out.writeShort(attributes.size());
		for (Attribute attribute : attributes) {
			out.writeShort(attribute.name());
			out.writeInt(attribute.body().length);
			out.write(attribute.body());
		}
	}
}
