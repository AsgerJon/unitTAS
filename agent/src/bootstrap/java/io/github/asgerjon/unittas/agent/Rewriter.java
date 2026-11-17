package io.github.asgerjon.unittas.agent;

import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassHierarchyResolver;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeBuilder;
import java.lang.classfile.CodeElement;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.Label;
import java.lang.classfile.MethodModel;
import java.lang.classfile.MethodTransform;
import java.lang.classfile.TypeKind;
import java.lang.classfile.instruction.ReturnInstruction;
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.MethodTypeDesc;
import java.lang.instrument.ClassFileTransformer;
import java.lang.reflect.AccessFlag;
import java.security.ProtectionDomain;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Puts the hooks into the game's classes as they load, by the JDK's own class-file API (java.lang.classfile): a BEFORE
 * hook's call at the method's start, which returns at once with the hook's value unless that is the pass mark; an
 * AFTER hook's call before each of its returns. The code put in names JDK classes only, never one of unitTAS's: a
 * loader may keep the game from seeing the agent's jar (Fabric's Knot does), so the hooks reach the bridge as a
 * java.util.function.BiFunction kept in the JVM's system properties (Bridge.HOOKS), the pass mark beside it
 * (Bridge.PASS). A call gives it the hook's name and an array: the hooked class, the instance (null for a static
 * method) and the method's arguments, boxed. A class the game loads under Fabric is seen after Mixin has made it. A
 * class that can't be rewritten is said on the error stream and left as it was; the probe then reports it missing.
 */
final class Rewriter implements ClassFileTransformer {

	private static final ClassDesc SYSTEM = ClassDesc.of("java.lang.System");
	private static final ClassDesc PROPERTIES = ClassDesc.of("java.util.Properties");
	private static final ClassDesc FUNCTION = ClassDesc.of("java.util.function.BiFunction");
	private static final MethodTypeDesc GET_PROPERTIES = MethodTypeDesc.of(PROPERTIES);
	private static final MethodTypeDesc GET = MethodTypeDesc.of(ConstantDescs.CD_Object, ConstantDescs.CD_Object);
	private static final MethodTypeDesc APPLY = MethodTypeDesc.of(ConstantDescs.CD_Object, ConstantDescs.CD_Object,
		ConstantDescs.CD_Object);

	private final Map<String, List<Hooks.Hook>> byOwner = new HashMap<>();

	Rewriter(List<Hooks.Hook> hooks) {
		for (Hooks.Hook hook : hooks) {
			byOwner.computeIfAbsent(hook.owner(), owner -> new ArrayList<>()).add(hook);
		}
	}

	@Override
	public byte[] transform(ClassLoader loader, String name, Class<?> redefined, ProtectionDomain domain, byte[] bytes) {
		List<Hooks.Hook> hooks = byOwner.get(name);
		if (hooks == null) {
			return null;
		}
		try {
			byte[] rewritten = rewrite(loader, bytes, hooks);
			Bridge.rewritten(name);
			return rewritten;
		} catch (Throwable e) {
			System.err.println("[unitTAS] couldn't put the probe's hooks into " + name + ": " + e);
			e.printStackTrace();
			return null;
		}
	}

	private static byte[] rewrite(ClassLoader loader, byte[] bytes, List<Hooks.Hook> hooks) {
		// the stack maps are made again: the class hierarchy read from the loader's own class files, else the JDK's
		ClassLoader resolving = loader == null ? ClassLoader.getSystemClassLoader() : loader;
		ClassFile files = ClassFile.of(ClassFile.ClassHierarchyResolverOption.of(
			ClassHierarchyResolver.ofResourceParsing(resolving).orElse(ClassHierarchyResolver.defaultResolver())));
		ClassModel model = files.parse(bytes);
		ClassDesc owner = model.thisClass().asSymbol();
		ClassTransform transform = (builder, element) -> {
			if (element instanceof MethodModel method) {
				List<Hooks.Hook> mine = hooksOf(method, hooks);
				if (!mine.isEmpty()) {
					builder.transformMethod(method, MethodTransform.transformingCode(new Hooked(owner, method, mine)));
					return;
				}
			}
			builder.with(element);
		};
		return files.transformClass(model, transform);
	}

	private static List<Hooks.Hook> hooksOf(MethodModel method, List<Hooks.Hook> hooks) {
		List<Hooks.Hook> mine = new ArrayList<>();
		for (Hooks.Hook hook : hooks) {
			if (method.methodName().equalsString(hook.method())
				&& (hook.descriptor() == null || method.methodType().equalsString(hook.descriptor()))) {
				mine.add(hook);
			}
		}
		return mine;
	}

	/** One method's hooks put into its code. */
	private static final class Hooked implements CodeTransform {

		private final ClassDesc owner;
		private final boolean statics;
		private final MethodTypeDesc type;
		private final List<Hooks.Hook> before = new ArrayList<>();
		private final List<Hooks.Hook> after = new ArrayList<>();

		Hooked(ClassDesc owner, MethodModel method, List<Hooks.Hook> hooks) {
			this.owner = owner;
			this.statics = method.flags().has(AccessFlag.STATIC);
			this.type = method.methodTypeSymbol();
			for (Hooks.Hook hook : hooks) {
				(hook.when() == Hooks.When.BEFORE ? before : after).add(hook);
			}
		}

		@Override
		public void atStart(CodeBuilder code) {
			for (Hooks.Hook hook : before) {
				call(code, hook);
				// the hook's value: the pass mark goes on; anything else is the method's, returned at once
				Label pass = code.newLabel();
				code.dup();
				property(code, Bridge.PASS);
				code.if_acmpeq(pass);
				returnValue(code, type.returnType());
				code.labelBinding(pass);
				code.pop();
			}
		}

		@Override
		public void accept(CodeBuilder code, CodeElement element) {
			if (!after.isEmpty() && element instanceof ReturnInstruction) {
				for (Hooks.Hook hook : after) {
					call(code, hook);
					code.pop();
				}
			}
			code.with(element);
		}

		/** A system property's value: System.getProperties().get(key). */
		private static void property(CodeBuilder code, String key) {
			code.invokestatic(SYSTEM, "getProperties", GET_PROPERTIES);
			code.ldc(key);
			code.invokevirtual(PROPERTIES, "get", GET);
		}

		/**
		 * The bridge's apply(the hook's name, [the hooked class, this or null, the arguments boxed]), its value left on
		 * the stack.
		 */
		private void call(CodeBuilder code, Hooks.Hook hook) {
			property(code, Bridge.HOOKS);
			code.checkcast(FUNCTION);
			code.ldc(hook.id());
			List<ClassDesc> parameters = type.parameterList();
			code.loadConstant(parameters.size() + 2);
			code.anewarray(ConstantDescs.CD_Object);
			code.dup();
			code.loadConstant(0);
			code.ldc(owner);
			code.aastore();
			code.dup();
			code.loadConstant(1);
			if (statics) {
				code.aconst_null();
			} else {
				code.aload(0);
			}
			code.aastore();
			int slot = statics ? 0 : 1;
			for (int i = 0; i < parameters.size(); i++) {
				ClassDesc parameter = parameters.get(i);
				TypeKind kind = TypeKind.from(parameter);
				code.dup();
				code.loadConstant(i + 2);
				code.loadLocal(kind, slot);
				box(code, parameter);
				code.aastore();
				slot += kind.slotSize();
			}
			code.invokeinterface(FUNCTION, "apply", APPLY);
		}

		/** The hook's value, on the stack as an Object, returned as the method returns its type. */
		private static void returnValue(CodeBuilder code, ClassDesc returned) {
			if (returned.equals(ConstantDescs.CD_void)) {
				code.pop();
				code.return_();
				return;
			}
			if (!returned.isPrimitive()) {
				code.checkcast(returned);
				code.areturn();
				return;
			}
			ClassDesc boxed = boxOf(returned);
			code.checkcast(boxed);
			code.invokevirtual(boxed, returned.displayName() + "Value", MethodTypeDesc.of(returned));
			code.return_(TypeKind.from(returned));
		}

		private static void box(CodeBuilder code, ClassDesc type) {
			if (type.isPrimitive()) {
				ClassDesc boxed = boxOf(type);
				code.invokestatic(boxed, "valueOf", MethodTypeDesc.of(boxed, type));
			}
		}

		private static ClassDesc boxOf(ClassDesc primitive) {
			switch (primitive.descriptorString()) {
				case "Z": return ConstantDescs.CD_Boolean;
				case "B": return ConstantDescs.CD_Byte;
				case "C": return ConstantDescs.CD_Character;
				case "S": return ConstantDescs.CD_Short;
				case "I": return ConstantDescs.CD_Integer;
				case "J": return ConstantDescs.CD_Long;
				case "F": return ConstantDescs.CD_Float;
				case "D": return ConstantDescs.CD_Double;
				default: throw new IllegalArgumentException("no box for " + primitive);
			}
		}
	}
}
