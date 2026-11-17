package io.github.asgerjon.unittas.agent.game;

/** RenameCheck's game (SPEC.md 19.7 step 6b): a class with fields, methods, a static and an array, by Mojang's names. */
public class Entity {

	public static int made;

	public double x;

	public Entity() {
		made++;
	}

	public double getX() {
		return x;
	}

	public void tick() {
		x += 1;
	}

	public String describe() {
		return "entity at " + getX();
	}

	public static Entity[] many(int count) {
		Entity[] many = new Entity[count];
		for (int i = 0; i < count; i++) {
			many[i] = new Entity();
		}
		return many;
	}
}
