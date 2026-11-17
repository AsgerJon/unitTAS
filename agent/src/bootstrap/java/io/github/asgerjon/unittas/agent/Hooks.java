package io.github.asgerjon.unittas.agent;

import java.util.List;

/**
 * The game's methods the probe hooks (SPEC.md 19.7 step 5), by their class, name and descriptor in Mojang's names (26.x
 * is unobfuscated): each the counterpart of one of the 26.3 Fabric probe's mixins. A hook BEFORE is called at the
 * method's start, and may end it there (its value then the method's); a hook AFTER is called before each of its
 * returns.
 */
final class Hooks {

	enum When {
		BEFORE, AFTER
	}

	/** One hook: where, when, and its name the probe knows it by. A null descriptor takes the name's every method. */
	record Hook(String owner, String method, String descriptor, When when, String id) {
	}

	private static final String MINECRAFT = "net/minecraft/client/Minecraft";
	private static final String KEYBOARD = "net/minecraft/client/KeyboardHandler";
	private static final String MOUSE = "net/minecraft/client/MouseHandler";

	static final List<Hook> TABLE = List.of(
		// the game made: the probe dials (as 1.7.10's does from Minecraft's constructor)
		new Hook(MINECRAFT, "<init>", null, When.AFTER, "minecraft.made"),
		new Hook(MINECRAFT, "tick", "()V", When.BEFORE, "client.tick.start"),
		new Hook(MINECRAFT, "tick", "()V", When.AFTER, "client.tick.end"),
		// the window's title while the probe is awake (PROTOCOL.md 2.5)
		new Hook(MINECRAFT, "createTitle", "()Ljava/lang/String;", When.BEFORE, "window.title"),
		new Hook("net/minecraft/client/gui/Gui", "setScreen", "(Lnet/minecraft/client/gui/screens/Screen;)V",
			When.BEFORE, "screen.set"),
		new Hook("net/minecraft/server/MinecraftServer", "tickServer", "(Ljava/util/function/BooleanSupplier;)V",
			When.BEFORE, "server.tick.start"),
		new Hook("net/minecraft/server/MinecraftServer", "tickServer", "(Ljava/util/function/BooleanSupplier;)V",
			When.AFTER, "server.tick.end"),
		new Hook("net/minecraft/client/gui/components/ChatComponent", "addMessage",
			"(Lnet/minecraft/network/chat/Component;Lnet/minecraft/network/chat/MessageSignature;"
				+ "Lnet/minecraft/client/multiplayer/chat/GuiMessageSource;"
				+ "Lnet/minecraft/client/multiplayer/chat/GuiMessageTag;)V", When.BEFORE, "chat.line"),
		new Hook("net/minecraft/client/sounds/SoundManager", "play",
			"(Lnet/minecraft/client/resources/sounds/SoundInstance;)Lnet/minecraft/client/sounds/SoundEngine$PlayResult;",
			When.BEFORE, "sound.play"),
		// the real keyboard and mouse dropped before the game reads them, the pointer never grabbed (PROTOCOL.md 2.5)
		new Hook(KEYBOARD, "keyPress", "(JILnet/minecraft/client/input/KeyEvent;)V", When.BEFORE, "real.input"),
		new Hook(KEYBOARD, "charTyped", "(JLnet/minecraft/client/input/CharacterEvent;)V", When.BEFORE, "real.input"),
		new Hook(KEYBOARD, "textInput", "(JLjava/lang/String;)V", When.BEFORE, "real.input"),
		new Hook(MOUSE, "grabMouse", "()V", When.BEFORE, "real.input"),
		new Hook(MOUSE, "onButton", "(JLnet/minecraft/client/input/MouseButtonInfo;I)V", When.BEFORE, "real.input"),
		new Hook(MOUSE, "onMove", "(JDDDD)V", When.BEFORE, "real.input"),
		new Hook(MOUSE, "onScroll", "(JDD)V", When.BEFORE, "real.input"),
		new Hook(MOUSE, "onDrop", "(JLjava/util/List;)V", When.BEFORE, "real.input"),
		new Hook(MOUSE, "isMouseGrabbed", "()Z", When.BEFORE, "mouse.grabbed"));

	private Hooks() {
	}
}
